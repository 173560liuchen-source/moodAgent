import asyncio
import json
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from ..emotion_labels import EmotionLabel, normalize_emotion_label
from ..model_gateway import ModelGateway, ModelGatewayError
from ..config import EMOTION_REQUEST_TIMEOUT_SECONDS
from ..schemas import ChatMessage, ModelChatRequest
from .agent_prompts import EMOTION_PROMPT


EMOTION_AGENT_MAX_REPAIR_ATTEMPTS = 1


class EmotionAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    emotion: EmotionLabel = "unknown"
    anxiety: float = Field(default=0.0, ge=0.0, le=1.0)
    stress: float = Field(default=0.0, ge=0.0, le=1.0)
    depression: float = Field(default=0.0, ge=0.0, le=1.0)
    loneliness: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence: list[str] = Field(default_factory=list)
    insufficient_data: bool = False
    reason: str = ""
    parse_status: Literal["ok", "repaired", "fallback", "insufficient_data"] = "ok"
    prompt_version: str = EMOTION_PROMPT.version
    validation_warnings: list[str] = Field(default_factory=list)

    @field_validator("evidence")
    @classmethod
    def evidence_must_be_short(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if item and item.strip()]

    @field_validator("emotion", mode="before")
    @classmethod
    def normalize_emotion(cls, value: object) -> EmotionLabel:
        return normalize_emotion_label(value)


class EmotionAgent:
    name = "emotion"
    version = "4.4.0"
    prompt_name = EMOTION_PROMPT.name
    prompt_version = EMOTION_PROMPT.version

    EMOTION_SIGNAL_PATTERNS = (
        r"压力|焦虑|紧张|心慌|烦|累|很累|疲惫|崩溃|难受|害怕|担心|失眠|睡不着|早醒|赶\s*ddl|安排时间.{0,6}乱|效率(?:特别|很|比较)?低",
        r"孤独|没人理解|没朋友|不开心|低落|沮丧|绝望|委屈|痛苦|撑不住",
        r"兴趣|起床困难|没用|注意力|效率低|被推着走|害怕失败|不能失败|喘不过气",
        r"stress|anxiety|anxious|depressed|lonely|sad|tired|overwhelmed",
    )

    _DETERMINISTIC_SIGNALS: tuple[tuple[EmotionLabel, str, float], ...] = (
        ("anxious", r"焦虑|紧张|心慌|担心|坐立不安", 0.68),
        ("stressed", r"压力(?:很大|较大|特别大|太大)?|赶\s*ddl|安排时间.{0,6}乱|效率(?:特别|很|比较)?低|喘不过气|不堪重负|快撑不住|撑不住|崩溃|疲惫|很累|睡不着|失眠|早醒|夜醒", 0.72),
        ("sad", r"低落|沮丧|不开心|难过|什么都不想做|提不起兴趣|起床困难|觉得自己没用|绝望", 0.66),
        ("lonely", r"孤独|孤单|没人理解(?:我)?|没有人理解(?:我)?|没朋友|被排斥", 0.70),
        ("fearful", r"害怕|恐惧|怕得", 0.68),
        ("angry", r"生气|愤怒|火大", 0.66),
        ("calm", r"平静|放松|好多了|轻松多了", 0.62),
    )
    _DEGRADED_SIGNALS: tuple[tuple[EmotionLabel, str, float], ...] = (
        ("anxious", r"烦躁|心里不踏实|静不下来|总往坏处想", 0.46),
        ("stressed", r"烦|累|难受|痛苦|注意力(?:很差|下降|不集中)?|效率低|被推着走|不能失败|扛不住", 0.48),
        ("sad", r"委屈|没用|没有动力|兴趣下降|提不起劲|不想起床", 0.46),
        ("lonely", r"没人陪|没有支持|融不进去|像被隔开", 0.46),
        ("fearful", r"不敢面对|总觉得会出事", 0.44),
        ("angry", r"憋着一股火|想发火", 0.44),
    )
    _NEGATION_PREFIX = re.compile(r"(?:没有|并不|已经不|不再|没那么|不是很|不太|毫不)[^，。！？!?；;]{0,4}$")
    _THIRD_PERSON = re.compile(r"朋友|同学|同事|室友|家人|父母|孩子|老师|患者|来访者|他|她|他们|她们")
    _FIRST_PERSON = re.compile(r"我|本人")
    _DEGREE_WEAK = re.compile(r"有点|稍微|一点|轻微")
    _DEGREE_STRONG = re.compile(r"非常|特别|十分|极其|太|很|快要|几乎")
    _DEGREE_PERSISTENT = re.compile(r"持续|一直|最近总是|这几天|好多天|反复")
    _FIRST_PERSON_STATE = re.compile(
        r"我(?:现在|最近|每天(?:都)?|总是|依然|仍然|一直|也|有点|稍微|非常|特别|很|感到|感觉|觉得|不太敢|不敢|害怕|快要|不再|没有|并不)|我自己|本人"
    )
    _SUBJECT_CONTINUATION = re.compile(r"^(?:也|还|而且|并且|同时|又)")

    def __init__(self, gateway: ModelGateway | None = None) -> None:
        self.gateway = gateway or ModelGateway()

    @classmethod
    def _fast_analysis(
        cls,
        message: str,
        history: list[ChatMessage] | None = None,
    ) -> EmotionAnalysis | None:
        """分析当前及最近四条用户消息，处理程度、否定、主体和时间衰减。"""
        user_turns = [item.content for item in (history or []) if item.role == "user"][-4:]
        turns = user_turns + [message]
        recency_weights = (0.35, 0.45, 0.60, 0.75, 1.0)[-len(turns):]
        scores: dict[EmotionLabel, float] = {
            label: 0.0 for label in ("anxious", "stressed", "sad", "lonely", "fearful", "angry", "calm")
        }
        evidence: list[str] = []
        negated_evidence: list[str] = []

        for turn, recency in zip(turns, recency_weights):
            previous_subject_scope = "unknown"
            for sentence in filter(None, re.split(r"[，。！？!?；;\n]+", turn)):
                has_first_person_state = bool(cls._FIRST_PERSON_STATE.search(sentence))
                has_third_person = bool(cls._THIRD_PERSON.search(sentence))
                if has_first_person_state:
                    subject_scope = "user"
                elif has_third_person:
                    subject_scope = "third_person"
                elif cls._SUBJECT_CONTINUATION.search(sentence.strip()):
                    subject_scope = previous_subject_scope
                else:
                    subject_scope = "unknown"
                previous_subject_scope = subject_scope
                if subject_scope == "third_person":
                    continue
                for label, pattern, base_score in cls._DETERMINISTIC_SIGNALS:
                    for match in re.finditer(pattern, sentence, flags=re.IGNORECASE):
                        prefix = sentence[max(0, match.start() - 10):match.start()]
                        if label != "calm" and cls._NEGATION_PREFIX.search(prefix):
                            phrase = f"{prefix}{match.group(0)}".strip()
                            negated_evidence.append(phrase[-18:])
                            scores["calm"] = max(scores["calm"], 0.55 * recency)
                            continue
                        context = sentence[max(0, match.start() - 8):min(len(sentence), match.end() + 4)]
                        degree = 1.0
                        if cls._DEGREE_WEAK.search(context):
                            degree *= 0.72
                        if cls._DEGREE_STRONG.search(context):
                            degree *= 1.18
                        if cls._DEGREE_PERSISTENT.search(sentence):
                            degree *= 1.12
                        scores[label] = min(1.0, scores[label] + base_score * degree * recency)
                        if match.group(0) not in evidence:
                            evidence.append(match.group(0))

        if not evidence and not negated_evidence:
            return None
        dominant = max(scores, key=scores.get)
        if scores[dominant] <= 0:
            return None
        anxiety = scores["anxious"]
        stress = scores["stressed"]
        depression = scores["sad"]
        loneliness = scores["lonely"]
        return EmotionAnalysis(
            emotion=dominant,
            anxiety=round(anxiety, 3),
            stress=round(stress, 3),
            depression=round(depression, 3),
            loneliness=round(loneliness, 3),
            confidence=round(min(0.92, 0.68 + max(scores.values()) * 0.22), 3),
            evidence=(evidence + negated_evidence)[:4],
            insufficient_data=False,
            reason="基于当前及最近用户消息中的程度、否定、主体与时间顺序进行确定性分析。",
            parse_status="ok",
            prompt_version=EMOTION_PROMPT.version,
            validation_warnings=["deterministic_fast_path", "deterministic_context_fast_path"],
        )

    @classmethod
    def _degraded_local_analysis(
        cls,
        message: str,
        history: list[ChatMessage] | None,
        error_type: str,
    ) -> EmotionAnalysis | None:
        """模型不可用时，以较低置信度返回可解释的本地规则结果。"""
        direct = cls._fast_analysis(message, history)
        if direct is not None:
            return direct.model_copy(update={
                "confidence": min(direct.confidence, 0.58),
                "reason": "模型服务未在时限内返回，已使用本地情绪规则完成降级判断。",
                "parse_status": "fallback",
                "validation_warnings": direct.validation_warnings + [
                    f"model_gateway_error:{error_type}",
                    "local_rule_fallback",
                ],
            })

        user_turns = [item.content for item in (history or []) if item.role == "user"][-4:]
        turns = user_turns + [message]
        recency_weights = (0.35, 0.45, 0.60, 0.75, 1.0)[-len(turns):]
        scores: dict[EmotionLabel, float] = {
            label: 0.0 for label in ("anxious", "stressed", "sad", "lonely", "fearful", "angry", "calm")
        }
        evidence: list[str] = []

        for turn, recency in zip(turns, recency_weights):
            previous_subject_scope = "unknown"
            for sentence in filter(None, re.split(r"[，。！？!?；;\n]+", turn)):
                if cls._FIRST_PERSON_STATE.search(sentence):
                    subject_scope = "user"
                elif cls._THIRD_PERSON.search(sentence):
                    subject_scope = "third_person"
                elif cls._SUBJECT_CONTINUATION.search(sentence.strip()):
                    subject_scope = previous_subject_scope
                else:
                    subject_scope = "unknown"
                previous_subject_scope = subject_scope
                if subject_scope == "third_person":
                    continue
                for label, pattern, base_score in cls._DEGRADED_SIGNALS:
                    for match in re.finditer(pattern, sentence, flags=re.IGNORECASE):
                        prefix = sentence[max(0, match.start() - 10):match.start()]
                        if cls._NEGATION_PREFIX.search(prefix):
                            continue
                        context = sentence[max(0, match.start() - 8):min(len(sentence), match.end() + 4)]
                        degree = 0.72 if cls._DEGREE_WEAK.search(context) else 1.0
                        if cls._DEGREE_STRONG.search(context):
                            degree *= 1.15
                        if cls._DEGREE_PERSISTENT.search(sentence):
                            degree *= 1.10
                        scores[label] = min(1.0, scores[label] + base_score * degree * recency)
                        if match.group(0) not in evidence:
                            evidence.append(match.group(0))

        if not evidence:
            return None
        dominant = max(scores, key=scores.get)
        return EmotionAnalysis(
            emotion=dominant,
            anxiety=round(scores["anxious"], 3),
            stress=round(scores["stressed"], 3),
            depression=round(scores["sad"], 3),
            loneliness=round(scores["lonely"], 3),
            confidence=round(min(0.55, 0.32 + scores[dominant] * 0.30), 3),
            evidence=evidence[:4],
            insufficient_data=False,
            reason="模型服务未在时限内返回，已使用扩展本地规则完成低置信度降级判断。",
            parse_status="fallback",
            prompt_version=EMOTION_PROMPT.version,
            validation_warnings=[
                f"model_gateway_error:{error_type}",
                "local_rule_fallback",
            ],
        )

    @classmethod
    def _has_observable_signal(cls, text: str) -> bool:
        return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in cls.EMOTION_SIGNAL_PATTERNS)

    @staticmethod
    def _source_text(message: str, history: list[ChatMessage] | None = None) -> str:
        user_turns = [item.content for item in (history or []) if item.role == "user"][-4:]
        history_text = "\n".join(user_turns)
        return f"{history_text}\n{message}".strip()

    @staticmethod
    def _extract_json_text(content: str) -> str:
        text = content.strip()
        fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.IGNORECASE | re.DOTALL)
        if fenced:
            text = fenced.group(1).strip()
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            text = text[start : end + 1]
        return text

    @classmethod
    def _parse_raw(cls, content: str) -> EmotionAnalysis:
        text = cls._extract_json_text(content)
        payload = json.loads(text)
        return EmotionAnalysis.model_validate(payload)

    @staticmethod
    def _normalize_for_match(text: str) -> str:
        return re.sub(r"\s+", "", text)

    @classmethod
    def _validate_evidence(cls, analysis: EmotionAnalysis, source_text: str) -> EmotionAnalysis:
        source_normalized = cls._normalize_for_match(source_text)
        valid_evidence: list[str] = []
        warnings = list(analysis.validation_warnings)

        for item in analysis.evidence:
            if cls._normalize_for_match(item) in source_normalized:
                valid_evidence.append(item)
            else:
                warnings.append(f"evidence_not_found:{item[:40]}")

        if analysis.evidence and not valid_evidence:
            warnings.append("all_evidence_removed")

        max_signal = max(analysis.anxiety, analysis.stress, analysis.depression, analysis.loneliness)
        confidence = analysis.confidence
        insufficient_data = analysis.insufficient_data
        reason = analysis.reason

        if not valid_evidence and max_signal >= 0.2:
            confidence = min(confidence, 0.2)
            insufficient_data = True
            reason = reason or "模型给出了情绪分数，但没有提供可定位的用户原文证据。"
            warnings.append("confidence_capped_due_to_missing_evidence")

        if insufficient_data:
            confidence = min(confidence, 0.2)

        return analysis.model_copy(
            update={
                "evidence": valid_evidence,
                "confidence": confidence,
                "insufficient_data": insufficient_data,
                "reason": reason,
                "validation_warnings": warnings,
                "prompt_version": EMOTION_PROMPT.version,
            }
        )

    @staticmethod
    def _insufficient(reason: str) -> EmotionAnalysis:
        return EmotionAnalysis(
            emotion="unknown",
            anxiety=0.0,
            stress=0.0,
            depression=0.0,
            loneliness=0.0,
            confidence=0.1,
            evidence=[],
            insufficient_data=True,
            reason=reason,
            parse_status="insufficient_data",
            prompt_version=EMOTION_PROMPT.version,
        )

    @staticmethod
    def _fallback(reason: str, warnings: list[str] | None = None) -> EmotionAnalysis:
        return EmotionAnalysis(
            emotion="unknown",
            confidence=0.0,
            evidence=[],
            insufficient_data=True,
            reason=reason,
            parse_status="fallback",
            prompt_version=EMOTION_PROMPT.version,
            validation_warnings=warnings or [],
        )

    async def _call_model(self, messages: list[ChatMessage]) -> str:
        result = await asyncio.wait_for(
            self.gateway.chat(ModelChatRequest(messages=messages, temperature=0.0, max_tokens=220)),
            timeout=EMOTION_REQUEST_TIMEOUT_SECONDS,
        )
        return result.content

    async def _repair_json(self, raw_content: str, parse_error: str) -> str:
        repair_prompt = (
            "请把下面模型输出修复为严格 JSON 对象。"
            "只能返回 JSON，不要解释。字段必须包含："
            "emotion, anxiety, stress, depression, loneliness, confidence, evidence, "
            "insufficient_data, reason。"
            "emotion只能是 anxious, stressed, sad, lonely, fearful, angry, calm, unknown 之一。\n"
            f"解析错误：{parse_error}\n"
            f"原始输出：{raw_content}"
        )
        return await self._call_model(
            [
                ChatMessage(role="system", content=EMOTION_PROMPT.content),
                ChatMessage(role="user", content=repair_prompt),
            ]
        )

    async def analyze(
        self,
        message: str,
        history: list[ChatMessage] | None = None,
    ) -> EmotionAnalysis:
        source_text = self._source_text(message, history)
        if not self._has_observable_signal(source_text):
            return self._insufficient("用户文本中没有足够明确的情绪线索。")
        fast_result = self._fast_analysis(message, history)
        if fast_result is not None:
            return fast_result

        messages = [ChatMessage(role="system", content=EMOTION_PROMPT.content)]
        if history:
            messages.extend(history[-12:])
        messages.append(ChatMessage(role="user", content=message))

        try:
            raw_content = await self._call_model(messages)
        except (ModelGatewayError, asyncio.TimeoutError) as exc:
            degraded = self._degraded_local_analysis(
                message,
                history,
                type(exc).__name__,
            )
            if degraded is not None:
                return degraded
            return self._fallback(
                "模型服务暂时不可用，情绪分析进入降级结果。",
                warnings=[f"model_gateway_error:{type(exc).__name__}"],
            )
        try:
            analysis = self._parse_raw(raw_content)
            return self._validate_evidence(analysis, source_text)
        except (json.JSONDecodeError, ValidationError, TypeError, ValueError) as exc:
            last_error = exc

        for _ in range(EMOTION_AGENT_MAX_REPAIR_ATTEMPTS):
            try:
                repaired_content = await self._repair_json(raw_content, str(last_error))
                analysis = self._parse_raw(repaired_content)
                analysis = analysis.model_copy(update={"parse_status": "repaired"})
                return self._validate_evidence(analysis, source_text)
            except (json.JSONDecodeError, ValidationError, TypeError, ValueError) as exc:
                last_error = exc

        return self._fallback(
            "模型未返回可解析的结构化情绪分析结果。",
            warnings=[f"parse_error:{last_error}"],
        )
