import asyncio
import json
import os
import re
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ..model_gateway import ModelGateway, ModelGatewayError
from ..schemas import ChatMessage, ModelChatRequest
from .agent_prompts import CRISIS_PROMPT


CRISIS_AGENT_MAX_REPAIR_ATTEMPTS = 1


SignalType = Literal[
    "self_harm_ideation",
    "harm_to_others_ideation",
    "plan",
    "tool",
    "tool_access",
    "tool_focus",
    "time",
    "place",
    "immediacy",
    "farewell",
    "hopelessness",
    "abuse_or_coercion",
]


class CrisisRuleHit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_id: str
    signal_type: SignalType
    severity: Literal["low", "medium", "high"]
    evidence: str
    source: Literal["current", "history"] = "current"
    turn_index: int | None = None
    role: Literal["user"] = "user"


class CrisisHistoryState(BaseModel):
    """会话级危机状态；由后端随审计结果持久化并在下一轮回传。"""

    model_config = ConfigDict(extra="ignore")

    highest_recent_level: Literal["low", "medium", "high"] = "low"
    active_plan: bool = False
    tool_access: bool = False
    time_window: str | None = None
    place: str | None = None
    last_high_risk_turn: int | None = None
    safety_confirmed: bool = False
    human_handoff_status: Literal["none", "recommended", "accepted", "completed"] = "none"


class CrisisAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level: Literal["low", "medium", "high"] = "low"
    self_harm: bool = False
    harm_to_others: bool = False
    immediacy: Literal["none", "possible", "immediate"] = "none"
    plan_present: bool = False
    tool_present: bool = False
    time_present: bool = False
    place_present: bool = False
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence: list[str] = Field(default_factory=list)
    action: Literal["normal_support", "check_in", "crisis_response"] = "normal_support"
    requires_human_review: bool = False
    hard_rule_triggered: bool = False
    rule_hits: list[CrisisRuleHit] = Field(default_factory=list)
    decision_source: Literal[
        "rules",
        "model",
        "rules_over_model",
        "model_with_rules",
        "fallback",
        "repaired",
    ] = "model"
    model_level: Literal["low", "medium", "high"] | None = None
    model_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    crisis_response: str = ""
    parse_status: Literal["ok", "repaired", "fallback"] = "ok"
    prompt_version: str = CRISIS_PROMPT.version
    validation_warnings: list[str] = Field(default_factory=list)
    history_state: CrisisHistoryState = Field(default_factory=CrisisHistoryState)


@dataclass(frozen=True)
class CrisisRuleSpec:
    rule_id: str
    signal_type: SignalType
    severity: Literal["low", "medium", "high"]
    pattern: str


SCHOOL_COUNSELING_CONTACT = os.getenv("MOODAPP_SCHOOL_COUNSELING_CONTACT", "学校心理中心")
LOCAL_EMERGENCY_CONTACT = os.getenv("MOODAPP_LOCAL_EMERGENCY_CONTACT", "当地急救电话")
CRISIS_HOTLINE_CONTACT = os.getenv("MOODAPP_CRISIS_HOTLINE_CONTACT", "当地危机干预热线")
CRISIS_MODEL_TIMEOUT_SECONDS = float(os.getenv("MOODAPP_CRISIS_MODEL_TIMEOUT_SECONDS", "3"))
CRISIS_MODEL_MAX_TOKENS = int(os.getenv("MOODAPP_CRISIS_MODEL_MAX_TOKENS", "512"))


CRISIS_RESPONSE_TEMPLATES = {
    "high": (
        "我很担心你现在的安全，也谢谢你告诉我这些。你现在是否正在实施，或准备马上实施？"
        "请先把药物、刀具等危险物交给身边可信任的人，并离开天台、河边等危险地点；不要独处。"
        f"请立即联系身边可信任的人和{SCHOOL_COUNSELING_CONTACT}；如果危险正在发生，请拨打{LOCAL_EMERGENCY_CONTACT}，"
        f"也可以联系{CRISIS_HOTLINE_CONTACT}。本系统不能替代紧急医疗或专业危机救助。"
    ),
    "medium": (
        "谢谢你把这些感受说出来。为了确认你的安全，请告诉我：是否有具体计划？是否已经准备或拿到工具？"
        "预计什么时候、在哪里？你现在是否独处，身边是否有可以马上联系并陪伴你的人？"
        f"如果已有计划、工具或临近时间，请立刻联系可信任的人和{SCHOOL_COUNSELING_CONTACT}。"
    ),
    "low": "当前没有检测到明确危机信号，可以继续进行支持性对话和情绪梳理。",
}


class CrisisAgent:
    name = "crisis"
    version = "5.2.0"
    prompt_name = CRISIS_PROMPT.name
    prompt_version = CRISIS_PROMPT.version

    LOW_RISK_FAST_PATTERNS = (
        r"学习压力(?:很大|较大|有点大)",
        r"考试压力(?:很大|较大|有点大)",
        r"考试(?:前|临近|期间)?.{0,10}(?:有点|比较|轻微)?(?:焦虑|紧张|压力)",
        r"最近.{0,10}(?:有点|比较|轻微)(?:焦虑|紧张)",
        r"(?:还|仍|依然)?可以正常(?:上课|学习|生活|工作)",
        r"作业(?:很多|太多)",
        r"最近(?:有点|比较|很)?紧张",
        r"对(?:什么|很多事情)都没(?:有)?兴趣",
        r"起床(?:也|都)?(?:很|比较)?困难",
        r"觉得自己(?:很|特别)?没用",
        r"(?:我是不是|我是否|我有没有|告诉我.{0,8}是不是).{0,20}(?:抑郁症|焦虑症|双相情感障碍|心理疾病|精神疾病)",
        r"心理中心.{0,20}(?:预约|联系|开放时间|入口|地址|在哪里)",
        r"(?:预约不上|约不上).{0,15}(?:联系谁|找谁|怎么办)",
    )

    @classmethod
    def _clear_low_risk_evidence(cls, message: str) -> str | None:
        clean = (message or "").strip()
        if not clean or len(clean) > 160:
            return None
        for pattern in cls.LOW_RISK_FAST_PATTERNS:
            match = re.search(pattern, clean)
            if match:
                return match.group(0)
        return None

    @classmethod
    def _clear_non_self_context(cls, message: str) -> str | None:
        clean = (message or "").strip()
        if not clean or len(clean) > 240:
            return None
        context = cls.NON_SELF_CONTEXT_PATTERN.search(clean)
        if context and not cls.FIRST_PERSON_RISK_PATTERN.search(clean):
            return context.group(0)
        return None

    RULES: tuple[CrisisRuleSpec, ...] = (
        CrisisRuleSpec("self_ideation_001", "self_harm_ideation", "medium", r"自杀|自残|伤害自己|结束自己|结束生命|不想活|想死|不值得活|活着.{0,6}没意义"),
        CrisisRuleSpec("self_ideation_003", "self_harm_ideation", "high", r"(?:我|自己).{0,12}(?:准备|计划|打算).{0,16}(?:药|安眠药|农药|刀|绳子).{0,16}(?:结束自己|结束生命|自杀|自残|伤害自己|结束痛苦)"),
        CrisisRuleSpec("self_ideation_002", "self_harm_ideation", "medium", r"消失|不在了|不想继续|从这个世界下线|撑不过去|彻底结束|结束.{0,8}痛苦"),
        CrisisRuleSpec("tool_access_001", "tool_access", "medium", r"(?:把|拿着|手边|身边|桌上|枕边|已经有|准备了|准备).{0,10}(?:安眠药|药|刀|绳子|农药)|(?:安眠药|药|刀|绳子|农药).{0,12}(?:放在|就在|拿到|准备好|手边|桌上|结束生命|自杀|自残)"),
        CrisisRuleSpec("tool_focus_001", "tool_focus", "medium", r"盯着.{0,10}(?:它|安眠药|药|刀|绳子)|(?:安眠药|药|刀|绳子).{0,16}(?:想很多|盯着|反复看|发呆)"),
        CrisisRuleSpec("harm_other_001", "harm_to_others_ideation", "medium", r"伤害他人|伤害他|杀人|报复|付出代价|找他算账"),
        CrisisRuleSpec("harm_other_002", "harm_to_others_ideation", "medium", r"恨.{0,12}(同学|老师|室友|朋友).{0,12}(伤害|报复|算账)"),
        CrisisRuleSpec("plan_001", "plan", "high", r"准备|计划|打算|想好|决定|安排好|已经想过|已经计划"),
        CrisisRuleSpec("tool_001", "tool", "high", r"安眠药|药物|药|刀|美工刀|绳子|煤气|农药|工具|高处"),
        CrisisRuleSpec("time_001", "time", "high", r"今晚|今天晚上|现在|马上|立刻|一会儿|待会儿|凌晨|明天去"),
        CrisisRuleSpec("place_001", "place", "high", r"宿舍|天台|楼顶|阳台|河边|桥上|家里|高处"),
        CrisisRuleSpec("farewell_001", "farewell", "medium", r"再见了|永别|以后就见不到|最后一次|谢谢你们以前"),
        CrisisRuleSpec("hopeless_001", "hopelessness", "medium", r"撑不住|彻底没希望|没人能帮我|活着太痛苦|大家.{0,8}更轻松"),
        CrisisRuleSpec(
            "abuse_coercion_001",
            "abuse_or_coercion",
            "medium",
            r"(?:有人|同学|室友|老师|家人|他|她|他们).{0,12}(?:一直|反复|持续)?(?:威胁|恐吓|逼迫|勒索).{0,12}(?:我|不让我|不许我|逼我)",
        ),
        CrisisRuleSpec(
            "abuse_secrecy_001",
            "abuse_or_coercion",
            "medium",
            r"(?:不让我|不许我|逼我).{0,10}(?:告诉|求助|报警|联系).{0,8}(?:老师|家人|辅导员|学校|警察)?",
        ),
    )

    CONTEXTUAL_ONLY_SIGNALS = {"plan", "tool", "time", "place"}
    NON_SELF_CONTEXT_PATTERN = re.compile(r"新闻|报道|论文|作业|歌词|电影|小说|医学咨询|术语|朋友说|同学说|患者|来访者", re.IGNORECASE)
    FIRST_PERSON_RISK_PATTERN = re.compile(r"(?:我|自己).{0,16}(?:想死|不想活|自杀|自残|伤害|计划|准备|打算|撑不住|结束)", re.IGNORECASE)

    SAFETY_CONFIRMATION_PATTERNS = (
        re.compile(r"(?:现在|目前).{0,8}(?:没有|不会).{0,8}(?:实施|自杀|自残|伤害).{0,8}(?:想法|打算|计划)?|我不会实施", re.IGNORECASE),
        re.compile(r"(?:药|刀|绳子|工具).{0,12}(?:交给|拿走|收走|放远|远离)|(?:已经|我已).{0,8}(?:离开|远离).{0,8}(?:工具|危险地点|天台|河边|高处)", re.IGNORECASE),
        re.compile(r"(?:有人陪|有人在身边|不再独处|和.{0,8}在一起)", re.IGNORECASE),
        re.compile(r"(?:愿意|会|已经).{0,6}(?:联系|求助).{0,12}(?:老师|家人|朋友|心理中心|急救|热线|辅导员)", re.IGNORECASE),
    )

    def __init__(self, gateway: ModelGateway | None = None) -> None:
        self.gateway = gateway or ModelGateway()

    @staticmethod
    def _source_text(message: str, history: list[ChatMessage] | None = None) -> str:
        # 硬规则只能引用用户自己说过的话。若把 assistant 的安全核查问题
        # 一并扫描，“是否有计划、工具或时间”等提问会被误当成用户风险证据。
        recent_text = "\n".join(
            item.content for item in (history or [])[-12:] if item.role == "user"
        )
        return f"{recent_text}\n{message}".strip()

    @classmethod
    def _rule_scan(
        cls,
        text: str,
        *,
        source: Literal["current", "history"] = "current",
        turn_index: int | None = None,
    ) -> list[CrisisRuleHit]:
        if cls.NON_SELF_CONTEXT_PATTERN.search(text) and not cls.FIRST_PERSON_RISK_PATTERN.search(text):
            return []
        hits: list[CrisisRuleHit] = []
        for rule in cls.RULES:
            for match in re.finditer(rule.pattern, text, flags=re.IGNORECASE):
                evidence = match.group(0).strip()
                if evidence:
                    hits.append(
                        CrisisRuleHit(
                            rule_id=rule.rule_id,
                            signal_type=rule.signal_type,
                            severity=rule.severity,
                            evidence=evidence,
                            source=source,
                            turn_index=turn_index,
                        )
                    )
        return hits

    @classmethod
    def _rule_scan_user_turns(
        cls,
        message: str,
        history: list[ChatMessage] | None = None,
    ) -> list[CrisisRuleHit]:
        """规则只扫描用户轮次，并为审计证据保留准确来源。"""
        user_turns = [item for item in (history or [])[-12:] if item.role == "user"]
        hits: list[CrisisRuleHit] = []
        for index, item in enumerate(user_turns, start=1):
            hits.extend(cls._rule_scan(item.content, source="history", turn_index=index))
        hits.extend(cls._rule_scan(message, source="current", turn_index=len(user_turns) + 1))
        return hits

    @staticmethod
    def _has_signal(hits: list[CrisisRuleHit], signal_type: SignalType) -> bool:
        return any(hit.signal_type == signal_type for hit in hits)

    @classmethod
    def _rule_decision(cls, hits: list[CrisisRuleHit]) -> CrisisAnalysis | None:
        if not hits:
            return None

        meaningful_hits = [hit for hit in hits if hit.signal_type not in cls.CONTEXTUAL_ONLY_SIGNALS]
        if not meaningful_hits:
            return None

        self_harm = cls._has_signal(hits, "self_harm_ideation")
        harm_to_others = cls._has_signal(hits, "harm_to_others_ideation")
        farewell = cls._has_signal(hits, "farewell")
        hopelessness = cls._has_signal(hits, "hopelessness")
        abuse_or_coercion = cls._has_signal(hits, "abuse_or_coercion")
        plan_present = cls._has_signal(hits, "plan")
        tool_present = cls._has_signal(hits, "tool")
        tool_access = cls._has_signal(hits, "tool_access")
        tool_focus = cls._has_signal(hits, "tool_focus")
        time_present = cls._has_signal(hits, "time")
        place_present = cls._has_signal(hits, "place")
        context_present = plan_present or tool_present or tool_access or time_present or place_present

        hard_rule = (self_harm or harm_to_others) and context_present
        # 原子信号组合矩阵：持有并反复关注工具、或“告别+绝望”需要继续核查，
        # 但在没有自/他伤意图、时间暗示时不直接伪造为明确计划。
        combination_medium = (tool_access and tool_focus) or (farewell and hopelessness)
        if hard_rule:
            level: Literal["low", "medium", "high"] = "high"
            action: Literal["normal_support", "check_in", "crisis_response"] = "crisis_response"
            immediacy: Literal["none", "possible", "immediate"] = "immediate" if time_present else "possible"
            confidence = 0.98
            requires_human_review = True
        else:
            level = "medium"
            action = "check_in"
            immediacy = "possible"
            confidence = 0.9 if abuse_or_coercion else (0.88 if combination_medium else 0.84)
            requires_human_review = (
                self_harm
                or harm_to_others
                or farewell
                or hopelessness
                or abuse_or_coercion
                or combination_medium
            )

        evidence = list(dict.fromkeys(hit.evidence for hit in hits if hit.evidence))
        return CrisisAnalysis(
            level=level,
            self_harm=self_harm,
            harm_to_others=harm_to_others,
            immediacy=immediacy,
            plan_present=plan_present,
            tool_present=tool_present or tool_access,
            time_present=time_present,
            place_present=place_present,
            confidence=confidence,
            evidence=evidence[:8],
            action=action,
            requires_human_review=requires_human_review,
            hard_rule_triggered=hard_rule,
            rule_hits=hits[:16],
            decision_source="rules",
            crisis_response=CRISIS_RESPONSE_TEMPLATES[level],
            prompt_version=CRISIS_PROMPT.version,
        )

    @classmethod
    def _safety_confirmation_complete(cls, message: str) -> bool:
        return all(pattern.search(message) for pattern in cls.SAFETY_CONFIRMATION_PATTERNS)

    @staticmethod
    def _level_rank(level: Literal["low", "medium", "high"]) -> int:
        return {"low": 0, "medium": 1, "high": 2}[level]

    @classmethod
    def _apply_history_state(
        cls,
        analysis: CrisisAnalysis,
        hits: list[CrisisRuleHit],
        current_message: str,
        prior_state: CrisisHistoryState | dict[str, object] | None,
    ) -> CrisisAnalysis:
        previous = (
            prior_state
            if isinstance(prior_state, CrisisHistoryState)
            else CrisisHistoryState.model_validate(prior_state or {})
        )
        safety_confirmed = cls._safety_confirmation_complete(current_message)
        warnings = list(analysis.validation_warnings)

        # 同一会话内的历史高风险只能由完整安全确认解除；模型无权自行降级。
        if previous.highest_recent_level == "high" and not safety_confirmed and analysis.level != "high":
            analysis = analysis.model_copy(
                update={
                    "level": "high",
                    "action": "crisis_response",
                    "requires_human_review": True,
                    "hard_rule_triggered": True,
                    "decision_source": "rules_over_model",
                    "confidence": max(analysis.confidence, 0.98),
                    "evidence": list(dict.fromkeys(analysis.evidence + ["会话历史存在尚未解除的高风险状态"]))[:8],
                    "crisis_response": CRISIS_RESPONSE_TEMPLATES["high"],
                    "validation_warnings": warnings + ["historical_high_risk_lock"],
                }
            )
            warnings = list(analysis.validation_warnings)
        elif previous.highest_recent_level == "high" and safety_confirmed and analysis.level == "high":
            analysis = analysis.model_copy(
                update={
                    "level": "medium",
                    "action": "check_in",
                    "requires_human_review": True,
                    "hard_rule_triggered": False,
                    "confidence": max(analysis.confidence, 0.9),
                    "crisis_response": CRISIS_RESPONSE_TEMPLATES["medium"],
                    "validation_warnings": warnings + ["historical_high_risk_released_after_complete_safety_confirmation"],
                }
            )

        highest_level = analysis.level
        if not safety_confirmed and cls._level_rank(previous.highest_recent_level) > cls._level_rank(highest_level):
            highest_level = previous.highest_recent_level
        time_hit = next((hit.evidence for hit in reversed(hits) if hit.signal_type == "time"), None)
        place_hit = next((hit.evidence for hit in reversed(hits) if hit.signal_type == "place"), None)
        high_turns = [hit.turn_index for hit in hits if hit.turn_index is not None and hit.severity == "high"]
        state = CrisisHistoryState(
            highest_recent_level=highest_level,
            active_plan=(previous.active_plan or analysis.plan_present) and not safety_confirmed,
            tool_access=(previous.tool_access or analysis.tool_present) and not safety_confirmed,
            time_window=None if safety_confirmed else (time_hit or previous.time_window),
            place=None if safety_confirmed else (place_hit or previous.place),
            last_high_risk_turn=(max(high_turns) if high_turns else previous.last_high_risk_turn),
            safety_confirmed=safety_confirmed,
            human_handoff_status=(
                previous.human_handoff_status
                if previous.human_handoff_status in {"accepted", "completed"}
                else ("recommended" if analysis.requires_human_review else "none")
            ),
        )
        return analysis.model_copy(update={"history_state": state})

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
    def _parse_raw(cls, content: str) -> CrisisAnalysis:
        payload = json.loads(cls._extract_json_text(content))
        return CrisisAnalysis.model_validate(payload)

    @staticmethod
    def _normalize_for_match(text: str) -> str:
        return re.sub(r"\s+", "", text)

    @classmethod
    def _validate_evidence(cls, analysis: CrisisAnalysis, source_text: str) -> CrisisAnalysis:
        source_normalized = cls._normalize_for_match(source_text)
        warnings = list(analysis.validation_warnings)
        valid_evidence: list[str] = []
        for item in analysis.evidence:
            if cls._normalize_for_match(item) in source_normalized:
                valid_evidence.append(item)
            else:
                warnings.append(f"evidence_not_found:{item[:40]}")
        if analysis.evidence and not valid_evidence:
            warnings.append("all_evidence_removed")

        confidence = analysis.confidence
        requires_human_review = analysis.requires_human_review
        if analysis.level != "low" and not valid_evidence:
            confidence = min(confidence, 0.3)
            requires_human_review = True
            warnings.append("confidence_capped_due_to_missing_evidence")

        return analysis.model_copy(
            update={
                "evidence": valid_evidence,
                "confidence": confidence,
                "requires_human_review": requires_human_review,
                "prompt_version": CRISIS_PROMPT.version,
                "validation_warnings": warnings,
                "crisis_response": analysis.crisis_response or CRISIS_RESPONSE_TEMPLATES[analysis.level],
            }
        )

    @classmethod
    def _merge_rule_and_model(
        cls,
        rule_result: CrisisAnalysis | None,
        model_result: CrisisAnalysis,
        source_text: str,
    ) -> CrisisAnalysis:
        model_result = cls._validate_evidence(model_result, source_text)
        model_level = model_result.level
        model_confidence = model_result.confidence

        if rule_result and rule_result.hard_rule_triggered:
            return rule_result.model_copy(
                update={
                    "decision_source": "rules_over_model",
                    "model_level": model_level,
                    "model_confidence": model_confidence,
                    "validation_warnings": rule_result.validation_warnings
                    + [f"model_level:{model_level}", "hard_rule_overrode_model"],
                }
            )
        if rule_result and model_result.level == "low":
            return rule_result.model_copy(
                update={
                    "decision_source": "rules_over_model",
                    "model_level": model_level,
                    "model_confidence": model_confidence,
                    "validation_warnings": rule_result.validation_warnings
                    + [f"model_level:{model_level}", "rule_signal_prevented_low_downgrade"],
                }
            )
        if rule_result:
            merged_evidence = list(dict.fromkeys(rule_result.evidence + model_result.evidence))
            return model_result.model_copy(
                update={
                    "self_harm": model_result.self_harm or rule_result.self_harm,
                    "harm_to_others": model_result.harm_to_others or rule_result.harm_to_others,
                    "plan_present": model_result.plan_present or rule_result.plan_present,
                    "tool_present": model_result.tool_present or rule_result.tool_present,
                    "time_present": model_result.time_present or rule_result.time_present,
                    "place_present": model_result.place_present or rule_result.place_present,
                    "requires_human_review": model_result.requires_human_review or rule_result.requires_human_review,
                    "evidence": merged_evidence[:8],
                    "rule_hits": (rule_result.rule_hits + model_result.rule_hits)[:16],
                    "decision_source": "model_with_rules",
                    "model_level": model_level,
                    "model_confidence": model_confidence,
                    "crisis_response": CRISIS_RESPONSE_TEMPLATES[model_result.level],
                }
            )
        return model_result.model_copy(
            update={
                "decision_source": "model",
                "model_level": model_level,
                "model_confidence": model_confidence,
                "crisis_response": model_result.crisis_response or CRISIS_RESPONSE_TEMPLATES[model_result.level],
            }
        )

    @staticmethod
    def _fallback(reason: str, warnings: list[str] | None = None) -> CrisisAnalysis:
        # Deterministic rules and SafetyGate have already screened the current
        # turn before this branch. If neither current/history evidence produced
        # a rule hit, a model outage is a technical uncertainty—not clinical
        # evidence—and must not manufacture a human-review requirement.
        return CrisisAnalysis(
            level="low",
            confidence=0.0,
            evidence=[],
            action="normal_support",
            requires_human_review=False,
            decision_source="fallback",
            parse_status="fallback",
            prompt_version=CRISIS_PROMPT.version,
            validation_warnings=warnings or [reason],
            crisis_response=CRISIS_RESPONSE_TEMPLATES["low"],
        )

    async def _call_model(self, messages: list[ChatMessage]) -> str:
        result = await asyncio.wait_for(
            self.gateway.chat(
                ModelChatRequest(
                    messages=messages,
                    temperature=0.0,
                    max_tokens=CRISIS_MODEL_MAX_TOKENS,
                )
            ),
            timeout=CRISIS_MODEL_TIMEOUT_SECONDS,
        )
        return result.content

    async def _repair_json(self, raw_content: str, parse_error: str) -> str:
        repair_prompt = (
            "请把下面模型输出修复为严格 JSON 对象。只能返回 JSON，不要解释。"
            "字段必须包含：level, self_harm, harm_to_others, immediacy, plan_present, "
            "tool_present, time_present, place_present, confidence, evidence, action, "
            "requires_human_review。\n"
            f"解析错误：{parse_error}\n"
            f"原始输出：{raw_content}"
        )
        return await self._call_model(
            [
                ChatMessage(role="system", content=CRISIS_PROMPT.content),
                ChatMessage(role="user", content=repair_prompt),
            ]
        )

    async def assess(
        self,
        message: str,
        history: list[ChatMessage] | None = None,
        prior_state: CrisisHistoryState | dict[str, object] | None = None,
    ) -> CrisisAnalysis:
        source_text = self._source_text(message, history)
        rule_hits = self._rule_scan_user_turns(message, history)
        rule_result = self._rule_decision(rule_hits)
        if rule_result is None:
            rule_result = CrisisAnalysis()
        rule_result = self._apply_history_state(rule_result, rule_hits, message, prior_state)
        if rule_result and rule_result.hard_rule_triggered:
            return rule_result

        low_risk_evidence = self._clear_low_risk_evidence(message)
        non_self_context = self._clear_non_self_context(message)
        if (
            (low_risk_evidence or non_self_context)
            and not rule_hits
            and rule_result.history_state.highest_recent_level == "low"
            and not rule_result.history_state.active_plan
            and not rule_result.history_state.tool_access
        ):
            return rule_result.model_copy(update={
                "level": "low",
                "confidence": 0.88,
                "evidence": [low_risk_evidence or non_self_context],
                "action": "normal_support",
                "requires_human_review": False,
                "decision_source": "rules",
                "model_level": None,
                "model_confidence": None,
                "crisis_response": CRISIS_RESPONSE_TEMPLATES["low"],
                "validation_warnings": [
                    "deterministic_non_self_context_fast_path"
                    if non_self_context
                    else "deterministic_low_risk_fast_path"
                ],
            })

        # 无规则命中时仍让语义模型判断；空的默认结果不参与阻止模型结果。
        merge_rule_result = rule_result if rule_hits or rule_result.history_state.highest_recent_level != "low" else None

        def finalize(result: CrisisAnalysis) -> CrisisAnalysis:
            return self._apply_history_state(result, rule_hits, message, prior_state)

        messages = [ChatMessage(role="system", content=CRISIS_PROMPT.content)]
        if history:
            messages.extend(history[-12:])
        messages.append(ChatMessage(role="user", content=message))

        try:
            raw_content = await self._call_model(messages)
        except (ModelGatewayError, TimeoutError, asyncio.TimeoutError) as exc:
            if merge_rule_result:
                return finalize(merge_rule_result.model_copy(
                    update={
                        "decision_source": "rules_over_model",
                        "model_level": None,
                        "model_confidence": None,
                        "parse_status": "fallback",
                        "validation_warnings": rule_result.validation_warnings
                        + [f"model_gateway_error:{type(exc).__name__}"],
                    }
                ))
            return finalize(self._fallback(
                "模型服务暂时不可用，危机语义判断进入保守降级。",
                warnings=[f"model_gateway_error:{type(exc).__name__}"],
            ))

        try:
            model_result = self._parse_raw(raw_content)
            return finalize(self._merge_rule_and_model(merge_rule_result, model_result, source_text))
        except (json.JSONDecodeError, ValidationError, TypeError, ValueError) as exc:
            last_error = exc

        for _ in range(CRISIS_AGENT_MAX_REPAIR_ATTEMPTS):
            try:
                repaired_content = await self._repair_json(raw_content, str(last_error))
                model_result = self._parse_raw(repaired_content)
                model_result = model_result.model_copy(update={"parse_status": "repaired"})
                return finalize(self._merge_rule_and_model(merge_rule_result, model_result, source_text))
            except (json.JSONDecodeError, ValidationError, TypeError, ValueError) as exc:
                last_error = exc

        if merge_rule_result:
            return finalize(merge_rule_result.model_copy(
                update={
                    "decision_source": "rules_over_model",
                    "model_level": None,
                    "model_confidence": None,
                    "validation_warnings": rule_result.validation_warnings + [f"model_parse_error:{last_error}"],
                }
            ))
        return finalize(self._fallback(
            "模型未返回可解析的危机筛查结果。",
            warnings=[f"parse_error:{last_error}"],
        ))
