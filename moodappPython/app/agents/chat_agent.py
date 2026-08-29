from __future__ import annotations

import asyncio

import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from pydantic import BaseModel, ConfigDict, Field

from ..model_gateway import ModelGateway, ModelGatewayError
from ..config import CHAT_MAX_TOKENS, CHAT_REQUEST_TIMEOUT_SECONDS
from ..rag.contracts import RetrievalCitation
from ..schemas import ChatMessage, ModelChatRequest, ModelChatResponse
from .agent_prompts import DIALOGUE_PROMPT


class DialogueCitation(BaseModel):
    """DialogueAgent 可使用的最小引用单元。

    允许从 RAG 的 RetrievalCitation 或普通 dict 转换而来。这里不保存用户聊天，
    只保存知识库引用片段的溯源信息。
    """

    model_config = ConfigDict(extra="forbid")

    source: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    category: str = Field(min_length=1)
    chunk_id: str = Field(min_length=1)
    content: str = Field(min_length=1)
    score: float = Field(ge=0.0, le=1.0)


@dataclass(frozen=True)
class DialoguePolicyContext:
    """对话生成前的策略上下文。

    该对象只承载编排层已经判断出的安全、风险和检索信息。
    DialogueAgent 不自行做风险定级，也不允许模型覆盖上游安全判断。
    """

    risk_level: str = "low"
    crisis_action: str = "normal_support"
    requires_human_review: bool = False
    emotion_summary: str | None = None
    profile_summary: str | None = None
    intervention_summary: str | None = None
    citations: list[DialogueCitation] = field(default_factory=list)


class DialogueValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    passed: bool
    warnings: list[str] = Field(default_factory=list)
    applied_fixes: list[str] = Field(default_factory=list)


class ChatAgent:
    """负责普通心理陪伴对话的智能体。

    企业级边界：
    - 不负责风险定级，只消费 Crisis/Risk/RAG 的结果；
    - 不允许模型输出疾病诊断、治疗承诺或伪造引用；
    - 中高风险时使用确定性安全提示兜底；
    - 保持 respond(message, history) 旧接口兼容。
    """

    name = "dialogue"
    version = "5.2.0"
    prompt_name = DIALOGUE_PROMPT.name
    prompt_version = DIALOGUE_PROMPT.version

    _diagnosis_patterns: tuple[tuple[re.Pattern[str], str], ...] = (
        (re.compile(r"你(可能)?(已经)?(患有|得了|是|属于)(重度|中度|轻度)?抑郁症"), "你现在可能有明显的抑郁相关情绪线索"),
        (re.compile(r"你(可能)?(已经)?(患有|得了|是|属于)(重度|中度|轻度)?焦虑症"), "你现在可能有明显的焦虑相关情绪线索"),
        (re.compile(r"诊断(为|是)[:：]?(抑郁症|焦虑症|双相情感障碍|精神疾病)"), "这不能作为医学诊断，只能作为情绪线索参考"),
        (re.compile(r"你就是(抑郁症|焦虑症|双相情感障碍|精神疾病)"), "这不能直接判断为疾病"),
    )
    _overpromise_patterns: tuple[tuple[re.Pattern[str], str], ...] = (
        (re.compile(r"我(一定|肯定|保证)能(治好|解决|帮你走出来)"), "我会尽力陪你一起梳理，但不能保证替代专业支持"),
        (re.compile(r"(一定|肯定|保证)(会没事|会好起来|不会出问题)"), "现在可以先做一件能降低风险的小事，并尽量联系可信任的人"),
        (re.compile(r"完全不用(担心|害怕)"), "你可以先把注意力放在眼前最安全、最可执行的一步"),
    )
    _diagnosis_terms = (
        "抑郁症", "焦虑症", "双相情感障碍", "躁郁症", "强迫症",
        "创伤后应激障碍", "精神疾病", "心理疾病",
    )
    _diagnosis_request_terms = (
        "我是不是", "我是否", "我有没有", "是不是已经得了", "是不是得了",
        "给我诊断", "帮我诊断", "直接诊断", "能不能诊断", "能否诊断",
        "给我确诊", "帮我确诊", "能不能确诊", "能否确诊",
        "判断我是不是", "告诉我是不是",
    )
    _unsupported_reference_pattern = re.compile(
        r"(参考(?:资料)?|引用|来源|根据.*?指南|文献显示|研究表明)[:：]?.*",
        re.IGNORECASE,
    )

    def __init__(self, gateway: ModelGateway | None = None) -> None:
        self.gateway = gateway or ModelGateway()
        self.last_validation = DialogueValidationResult(passed=True)

    async def respond(
        self,
        message: str,
        history: list[ChatMessage] | None = None,
        *,
        crisis: Any | None = None,
        risk: Any | None = None,
        rag_citations: list[RetrievalCitation | dict[str, Any]] | None = None,
        profile: dict[str, Any] | None = None,
        intervention: dict[str, Any] | None = None,
    ) -> ModelChatResponse:
        policy = self._build_policy_context(
            crisis=crisis,
            risk=risk,
            rag_citations=rag_citations,
            profile=profile,
            intervention=intervention,
        )
        messages = self._build_messages(message, history, policy)
        try:
            response = await asyncio.wait_for(
                self.gateway.chat(
                    ModelChatRequest(
                        messages=messages,
                        temperature=self._temperature(policy),
                        max_tokens=CHAT_MAX_TOKENS,
                    )
                ),
                timeout=CHAT_REQUEST_TIMEOUT_SECONDS,
            )
        except (ModelGatewayError, asyncio.TimeoutError) as exc:
            fallback_content = self._fallback_response(policy, message)
            fallback_content = self._ensure_diagnosis_boundary_response(
                fallback_content, message, policy
            )
            fallback_content, validation = self._validate_and_repair(
                fallback_content, policy, message
            )
            self.last_validation = validation.model_copy(
                update={
                    "warnings": validation.warnings + ["model_gateway_error"],
                    "applied_fixes": validation.applied_fixes + ["dialogue_fallback_response"],
                }
            )
            return ModelChatResponse(
                content=fallback_content,
                model="fallback_dialogue",
                usage={
                    "fallback": True,
                    "reason": "model_gateway_error",
                    "error_type": type(exc).__name__,
                },
            )
        response_content = self._repair_incomplete_completion(
            response.content,
            response.usage,
        )
        response_content = self._ensure_diagnosis_boundary_response(
            response_content, message, policy
        )
        safe_content, validation = self._validate_and_repair(
            response_content, policy, message
        )
        self.last_validation = validation
        return ModelChatResponse(
            content=safe_content,
            model=response.model,
            usage=response.usage,
        )

    async def respond_stream(
        self,
        message: str,
        history: list[ChatMessage] | None = None,
        *,
        on_chunk: Callable[[str], Awaitable[None]],
        crisis: Any | None = None,
        risk: Any | None = None,
        rag_citations: list[RetrievalCitation | dict[str, Any]] | None = None,
        profile: dict[str, Any] | None = None,
        intervention: dict[str, Any] | None = None,
    ) -> ModelChatResponse:
        """Generate a low-risk reply and emit it only after whole-reply validation.

        Citation normalization is a response-level operation. Applying it to
        individual streamed sentences would append a footer after every
        sentence and could make the evaluator delete adjacent body text.
        """
        policy = self._build_policy_context(
            crisis=crisis,
            risk=risk,
            rag_citations=rag_citations,
            profile=profile,
            intervention=intervention,
        )
        if (
            policy.risk_level != "low"
            or policy.requires_human_review
            or self._is_diagnosis_request(message)
        ):
            response = await self.respond(
                message,
                history,
                crisis=crisis,
                risk=risk,
                rag_citations=rag_citations,
                profile=profile,
                intervention=intervention,
            )
            await on_chunk(response.content)
            return response

        messages = self._build_messages(message, history, policy)
        raw_chunks: list[str] = []
        response_model = self.gateway.model_name
        stream_interrupted = False
        try:
            async with asyncio.timeout(CHAT_REQUEST_TIMEOUT_SECONDS):
                async for delta in self.gateway.stream_chat(
                    ModelChatRequest(
                        messages=messages,
                        temperature=self._temperature(policy),
                        max_tokens=CHAT_MAX_TOKENS,
                    )
                ):
                    if delta:
                        raw_chunks.append(delta)
        except (ModelGatewayError, asyncio.TimeoutError):
            stream_interrupted = True

        if not raw_chunks:
            # A streaming connection can fail or end empty independently of
            # the normal completion API. Recover once through that API before
            # showing a fixed local fallback.
            recovery = await self.respond(
                message,
                history,
                crisis=crisis,
                risk=risk,
                rag_citations=rag_citations,
                profile=profile,
                intervention=intervention,
            )
            await on_chunk(recovery.content)
            return ModelChatResponse(
                content=recovery.content,
                model=recovery.model,
                usage={
                    **recovery.usage,
                    "stream": True,
                    "recovered_from_stream_failure": True,
                },
            )

        streamed_content = self._repair_incomplete_completion(
            "".join(raw_chunks),
            {"finish_reason": "stream_end"},
        )
        raw_content = self._ensure_diagnosis_boundary_response(
            streamed_content, message, policy
        )
        safe_content, validation = self._validate_and_repair(
            raw_content, policy, message
        )
        self.last_validation = validation
        await on_chunk(safe_content)

        return ModelChatResponse(
            content=safe_content,
            model=response_model,
            usage={
                "stream": True,
                "stream_interrupted": stream_interrupted,
                "whole_reply_validated": True,
            },
        )

    @staticmethod
    def _fallback_response(policy: DialoguePolicyContext, message: str = "") -> str:
        if policy.risk_level == "high" or policy.crisis_action == "crisis_response":
            return (
                "我现在优先关心你的安全。请先不要独处，尽快联系身边可信任的人；"
                "如果危险正在发生，请立即联系当地急救服务、危机热线或学校心理中心。"
            )
        if policy.risk_level == "medium" or policy.requires_human_review:
            return (
                "我能感觉到你现在并不轻松。为了更稳妥地支持你，建议你尽快联系一位可信任的人，"
                "也可以预约学校心理中心；如果你愿意，也可以先告诉我此刻最困扰你的事情是什么。"
            )

        clean = (message or "").strip()
        if policy.citations and "预约" in clean and any(
            citation.category == "school_resources" for citation in policy.citations
        ):
            return (
                "学校心理中心通常可以通过学校官网、公众号、线上预约系统或现场服务台查询预约方式；"
                "如果暂时找不到入口，也可以先询问辅导员。预约时简要说明当前最困扰的问题、"
                "大概持续了多久，以及对上课、作业或日常生活的影响即可，不需要准备完整的故事。"
            )
        if any(term in clean for term in ("考试", "复习", "备考")) and any(
            term in clean for term in ("焦虑", "紧张", "睡眠", "睡不好", "失眠")
        ):
            return (
                "听起来考试临近让你有些焦虑，睡眠也受到了一点影响；你还能正常上课，说明目前的日常功能仍在维持。"
                "今晚可以先做一个低负担调整：睡前半小时停止刷题和看手机，把明天最重要的三件事写下来，"
                "再做几轮缓慢呼吸。如果连续一到两周仍明显睡不好，或开始影响上课和生活，"
                "可以考虑联系学校心理中心进一步聊聊。"
            )
        if any(term in clean for term in ("睡眠", "睡不好", "失眠", "睡不着")):
            return (
                "我注意到你提到了睡眠波动。今晚可以先把目标定得小一些：固定一个准备上床的时间，"
                "睡前半小时减少手机和高强度学习，并简单记下入睡时间和第二天的精神状态。"
                "如果这种情况持续一到两周或明显影响日常生活，建议联系学校心理中心或专业人员。"
            )
        return (
            "我在这里。你可以先把现在最具体的一件压力源写下来，再补充它持续了多久、"
            "对学习或生活有什么影响；我们可以从最容易处理的一小步开始梳理。"
        )

    @classmethod
    def _is_diagnosis_request(cls, message: str) -> bool:
        clean = (message or "").strip().lower()
        return (
            any(term in clean for term in cls._diagnosis_terms)
            and any(term in clean for term in cls._diagnosis_request_terms)
        )

    @classmethod
    def _ensure_diagnosis_boundary_response(
        cls,
        content: str,
        message: str,
        policy: DialoguePolicyContext,
    ) -> str:
        """为本人求诊问题添加确定性的非诊断边界，避免模型空答或直接下结论。"""
        if not cls._is_diagnosis_request(message):
            return content
        if policy.citations:
            boundary = (
                "我理解你希望得到一个明确答案，但我不能仅凭这一句话判断你是否患有某种心理疾病，"
                "也不能替代专业诊断。"
                "知识库资料说明，自评量表只能用于筛查和自我了解，不等同于临床诊断；"
                "判断时还需结合症状持续时间、日常功能和专业访谈。"
                "如果这种困扰持续或影响学习生活，建议联系学校心理中心或精神心理专科进行专业评估。"
            )
        else:
            boundary = (
                "我不能仅凭这一句话判断你是否患有某种心理疾病，也不能替代专业诊断。"
                "当前没有足够的可信依据支持疾病判断，因此我不会给出确诊结论；"
                "如果这种困扰持续或影响学习生活，建议联系学校心理中心或精神心理专科进行专业评估。"
            )
        # 不拼接模型自由生成内容：知识片段可能含“量表分数示例”，模型容易将其
        # 错当成当前用户的历史事实。引用页脚仍由统一校验流程添加。
        return boundary

    def _build_policy_context(
        self,
        *,
        crisis: Any | None,
        risk: Any | None,
        rag_citations: list[RetrievalCitation | dict[str, Any]] | None,
        profile: dict[str, Any] | None,
        intervention: dict[str, Any] | None,
    ) -> DialoguePolicyContext:
        risk_level = self._read_field(risk, "risk_level") or self._read_field(crisis, "level") or "low"
        crisis_action = self._read_field(crisis, "action") or "normal_support"
        requires_human_review = bool(
            self._read_field(risk, "requires_human_review")
            or self._read_field(crisis, "requires_human_review")
            or crisis_action in {"check_in", "crisis_response"}
            or risk_level in {"medium", "high"}
        )
        citations = self._normalize_citations(rag_citations or [])
        profile_summary = self._profile_summary(profile or {})
        intervention_summary = self._intervention_summary(intervention or {})
        return DialoguePolicyContext(
            risk_level=str(risk_level),
            crisis_action=str(crisis_action),
            requires_human_review=requires_human_review,
            profile_summary=profile_summary,
            intervention_summary=intervention_summary,
            citations=citations,
        )

    @staticmethod
    def _read_field(obj: Any, name: str) -> Any | None:
        if obj is None:
            return None
        if isinstance(obj, dict):
            return obj.get(name)
        return getattr(obj, name, None)

    @staticmethod
    def _profile_summary(profile: dict[str, Any]) -> str | None:
        if not profile:
            return None
        patch_items = profile.get("patch_items")
        if isinstance(patch_items, list):
            parts = [
                f"{item.get('category')}={item.get('value')}"
                for item in patch_items[:6]
                if isinstance(item, dict) and item.get("category") and item.get("value")
            ]
            if parts:
                return "；".join(parts)
        allowed_keys = (
            "stressors",
            "support_resources",
            "coping_methods",
            "communication_preference",
            "sleep_status",
            "study_status",
            "social_status",
        )
        parts: list[str] = []
        for key in allowed_keys:
            value = profile.get(key)
            if value:
                parts.append(f"{key}={value}")
        return "；".join(parts) if parts else None

    @staticmethod
    def _intervention_summary(intervention: dict[str, Any]) -> str | None:
        if not intervention:
            return None
        parts: list[str] = []
        level = intervention.get("intervention_level")
        strategy = intervention.get("strategy")
        if level:
            parts.append(f"level={level}")
        if strategy:
            parts.append(f"strategy={strategy}")
        actions = intervention.get("actions")
        if isinstance(actions, list):
            titles = [
                str(item.get("title"))
                for item in actions[:3]
                if isinstance(item, dict) and item.get("title")
            ]
            if titles:
                parts.append("actions=" + "、".join(titles))
        return "；".join(parts) if parts else None

    @staticmethod
    def _normalize_citations(
        citations: list[RetrievalCitation | dict[str, Any]],
    ) -> list[DialogueCitation]:
        normalized: list[DialogueCitation] = []
        seen: set[str] = set()
        for item in citations:
            raw = item.model_dump() if isinstance(item, BaseModel) else dict(item)
            chunk_id = str(raw.get("chunk_id", "")).strip()
            content = str(raw.get("content", "")).strip()
            source = str(raw.get("source", "")).strip()
            if not chunk_id or not content or not source or chunk_id in seen:
                continue
            score = raw.get("score", 0.0)
            try:
                safe_score = max(0.0, min(1.0, float(score)))
            except (TypeError, ValueError):
                safe_score = 0.0
            normalized.append(
                DialogueCitation(
                    source=source,
                    document_id=str(raw.get("document_id", source)).strip() or source,
                    title=str(raw.get("title") or source).strip(),
                    category=str(raw.get("category", "student_psychology")).strip(),
                    chunk_id=chunk_id,
                    content=content[:700],
                    score=safe_score,
                )
            )
            seen.add(chunk_id)
            if len(normalized) >= 3:
                break
        return normalized

    def _build_messages(
        self,
        message: str,
        history: list[ChatMessage] | None,
        policy: DialoguePolicyContext,
    ) -> list[ChatMessage]:
        system_prompt = "\n\n".join(
            part
            for part in [
                DIALOGUE_PROMPT.content,
                self._policy_prompt(policy),
                self._rag_prompt(policy.citations),
            ]
            if part
        )
        messages = [ChatMessage(role="system", content=system_prompt)]
        if history:
            messages.extend(history[-12:])
        messages.append(ChatMessage(role="user", content=message))
        return messages

    @staticmethod
    def _policy_prompt(policy: DialoguePolicyContext) -> str:
        lines = [
            "【上游安全与风险上下文】",
            f"- risk_level={policy.risk_level}",
            f"- crisis_action={policy.crisis_action}",
            f"- requires_human_review={policy.requires_human_review}",
            "你必须服从以上风险上下文，不得自行降低风险等级。",
            "低风险：以共情、澄清、轻量建议为主。",
            "中风险：共情后建议联系可信任的人、学校心理中心或线下支持，不制造恐慌。",
            "高风险：优先安全，建议不要独处，立即联系身边可信任的人、学校心理中心、当地急救或危机热线。",
        ]
        if policy.profile_summary:
            lines.append(f"【用户状态画像摘要】{policy.profile_summary}")
        if policy.intervention_summary:
            lines.append(f"【干预方案摘要】{policy.intervention_summary}")
            lines.append("回复应落实干预方案中的可执行动作，但不得编造未提供的建议。")
        return "\n".join(lines)

    @staticmethod
    def _rag_prompt(citations: list[DialogueCitation]) -> str:
        if not citations:
            return (
                "【知识库引用约束】本轮没有提供可引用的 RAG 资料。"
                "不得编造来源、文献、指南、研究结论或 chunk_id。"
            )
        blocks = ["【可使用的 RAG 引用】只能使用以下引用，不得编造其他来源："]
        for index, citation in enumerate(citations, start=1):
            blocks.append(
                f"[{index}] title={citation.title}; category={citation.category}; "
                f"document_id={citation.document_id}; chunk_id={citation.chunk_id}; "
                f"score={citation.score:.3f}; content={citation.content}"
            )
        blocks.append(
            "每条知识性建议必须由上面的原文片段支持。所有引用信息只供内部审计；"
            "用户回复中严禁输出参考资料页脚、资料标题、document_id、chunk_id、文件路径或检索分数。"
        )
        return "\n".join(blocks)

    @staticmethod
    def _temperature(policy: DialoguePolicyContext) -> float:
        if policy.risk_level == "high":
            return 0.05
        if policy.risk_level == "medium":
            return 0.1
        return 0.25

    def _validate_and_repair(
        self,
        content: str,
        policy: DialoguePolicyContext,
        message: str = "",
    ) -> tuple[str, DialogueValidationResult]:
        warnings: list[str] = []
        fixes: list[str] = []
        repaired = content.strip()

        repaired, diagnosis_fixed = self._replace_patterns(
            repaired, self._diagnosis_patterns
        )
        if diagnosis_fixed:
            warnings.append("diagnostic_language_detected")
            fixes.append("diagnostic_language_neutralized")

        repaired, promise_fixed = self._replace_patterns(
            repaired, self._overpromise_patterns
        )
        if promise_fixed:
            warnings.append("overpromise_language_detected")
            fixes.append("overpromise_language_neutralized")

        if not policy.citations:
            cleaned = self._remove_unsupported_references(repaired)
            if cleaned != repaired:
                repaired = cleaned
                warnings.append("unsupported_reference_detected")
                fixes.append("unsupported_reference_removed")
        else:
            repaired, citation_fixed = self._remove_user_facing_citations(
                repaired, policy.citations
            )
            if citation_fixed:
                warnings.append("user_facing_citation_detected")
                fixes.append("user_facing_citation_removed")

        if not repaired.strip():
            repaired = self._fallback_response(policy, message)
            warnings.append("empty_body_after_citation_cleanup")
            fixes.append("contextual_empty_reply_recovery")

        repaired, risk_fixed = self._ensure_risk_style(repaired, policy)
        if risk_fixed:
            warnings.append("risk_style_guardrail_applied")
            fixes.append("risk_support_text_added")

        repaired = self._normalize_length(repaired, policy)
        return repaired, DialogueValidationResult(
            passed=not warnings,
            warnings=warnings,
            applied_fixes=fixes,
        )

    @staticmethod
    def _replace_patterns(
        text: str,
        patterns: tuple[tuple[re.Pattern[str], str], ...],
    ) -> tuple[str, bool]:
        changed = False
        repaired = text
        for pattern, replacement in patterns:
            repaired, count = pattern.subn(replacement, repaired)
            changed = changed or count > 0
        return repaired, changed

    def _remove_unsupported_references(self, text: str) -> str:
        lines = []
        changed = False
        for line in text.splitlines():
            if self._unsupported_reference_pattern.search(line):
                line = self._unsupported_reference_pattern.sub("", line).rstrip()
                changed = True
            if line.strip():
                lines.append(line)
        return "\n".join(lines).strip() if changed else text

    @staticmethod
    def _remove_user_facing_citations(
        text: str,
        citations: list[DialogueCitation],
    ) -> tuple[str, bool]:
        # The full citation objects remain in the structured RAG/audit result.
        # The chat surface contains only answer prose; titles and identifiers stay
        # in the structured payload.
        cleaned = text
        for citation in citations:
            labels = {citation.title.strip(), citation.source.strip()}
            identifiers = {citation.document_id.strip(), citation.chunk_id.strip()}
            for label in filter(None, labels):
                for identifier in filter(None, identifiers):
                    cleaned = re.sub(
                        rf"\s*{re.escape(label)}\s*/\s*{re.escape(identifier)}",
                        "",
                        cleaned,
                        flags=re.IGNORECASE,
                    )
            for identifier in filter(None, identifiers):
                cleaned = re.sub(
                    rf"\s*/?\s*{re.escape(identifier)}",
                    "",
                    cleaned,
                    flags=re.IGNORECASE,
                )

        cleaned = re.sub(
            r"(?is)\s*(?:参考(?:资料)?|引用|来源)\s*[：:].*$",
            "",
            cleaned,
        ).strip()
        normalized = cleaned.strip()
        return normalized, normalized != text.strip()

    @staticmethod
    def _ensure_risk_style(
        text: str,
        policy: DialoguePolicyContext,
    ) -> tuple[str, bool]:
        if policy.risk_level not in {"medium", "high"} and not policy.requires_human_review:
            return text, False
        required_keywords = ("可信任的人", "学校心理中心", "急救", "危机热线", "不要独处")
        if any(keyword in text for keyword in required_keywords):
            return text, False
        if policy.risk_level == "high" or policy.crisis_action == "crisis_response":
            addition = (
                "我也想优先确认你的安全：请尽量不要独处，马上联系身边可信任的人，"
                "必要时联系学校心理中心、当地急救或危机热线。"
            )
        else:
            addition = (
                "如果这种状态持续加重，建议你今天就联系一位可信任的人，"
                "也可以预约学校心理中心获得线下支持。"
            )
        return f"{text.rstrip()}\n\n{addition}", True

    @staticmethod
    def _normalize_length(text: str, policy: DialoguePolicyContext) -> str:
        stripped = text.strip()
        footer = ""
        footer_match = re.search(r"(?s)\n{2,}(参考资料\s*[：:].*)$", stripped)
        if footer_match:
            footer = footer_match.group(1).strip()
            stripped = stripped[:footer_match.start()].strip()

        if policy.risk_level == "low":
            max_chars = 420 if policy.citations else 320
        else:
            # Medium/high-risk safety instructions must not be shortened to the
            # conversational limit.
            max_chars = 700

        if len(stripped) <= max_chars:
            normalized = stripped
        else:
            candidate = stripped[:max_chars].rstrip()
            boundary = max(candidate.rfind(mark) for mark in "。！？!?；;")
            if boundary >= max_chars // 2:
                normalized = candidate[:boundary + 1].rstrip()
            else:
                normalized = candidate.rstrip("，、：:；; ") + "。"

        if footer:
            return f"{normalized}\n\n{footer}" if normalized else footer
        return normalized

    @staticmethod
    def _repair_incomplete_completion(
        text: str,
        usage: dict[str, Any] | None,
    ) -> str:
        """Remove a cut-off tail when the provider reports a length stop."""
        stripped = (text or "").strip()
        if not stripped:
            return stripped
        finish_reason = str((usage or {}).get("finish_reason") or "").lower()
        complete_endings = ("。", "！", "？", "!", "?", "……", "》", "）", ")", "】")
        if finish_reason != "length" and stripped.endswith(complete_endings):
            return stripped

        boundary = max(stripped.rfind(mark) for mark in "。！？!?")
        minimum_boundary = 8 if finish_reason == "length" else max(24, len(stripped) // 2)
        if boundary >= minimum_boundary:
            repaired = stripped[:boundary + 1].rstrip()
        else:
            repaired = stripped.rstrip("，、：:；; ") + "。"
        if finish_reason == "length":
            repaired += "\n\n先从其中一个最容易做到的小步骤开始就可以。"
        return repaired
