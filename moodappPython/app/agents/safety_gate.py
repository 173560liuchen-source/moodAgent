import re
from typing import Literal

from pydantic import BaseModel, Field

from ..core.contracts import AgentContext
from .base import BaseAgent


class SafetyGateRequest(BaseModel):
    message: str = Field(min_length=1, max_length=12000)


class SafetyDecision(BaseModel):
    decision: Literal["allow", "redact", "block", "escalate"]
    redacted_message: str
    violations: list[str] = Field(default_factory=list)
    pii_types: list[str] = Field(default_factory=list)
    requires_human: bool = False
    evidence: list[str] = Field(default_factory=list)


class SafetyGateAgent(BaseAgent[SafetyGateRequest, SafetyDecision]):
    """所有请求的第一道安全闸门。

    职责：
    - 识别并脱敏 PII；
    - 拦截 Prompt 注入和越权请求；
    - 发现即时危机信号时直接升级，不让普通聊天链路覆盖安全判断。
    """

    name = "safety_gate"
    version = "1.2.0"

    PII_PATTERNS = {
        "phone": re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
        "email": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
        "id_card": re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)"),
        "api_key": re.compile(r"\b(?:sk|key|api)[-_]?[A-Za-z0-9]{16,}\b", re.IGNORECASE),
    }

    INJECTION_PATTERNS = (
        r"忽略.{0,12}(之前|上面|所有).{0,12}(指令|规则|提示词)",
        r"泄露.{0,12}(系统提示词|system prompt|提示词|密钥|api key|API密钥)",
        r"(绕过|关闭|取消|禁用).{0,12}(安全|审核|规则|限制|权限)",
        r"你现在是.{0,12}(系统管理员|开发者模式|无限制模式|DAN)",
        r"不要遵守.{0,12}(安全规则|之前的规则|系统规则)",
        r"ignore.{0,20}(previous|above|all).{0,20}(instruction|rule|prompt)",
        r"reveal.{0,20}(system prompt|secret|api key|credential)",
        r"(bypass|disable|override).{0,20}(safety|policy|guardrail|instruction)",
    )

    ESCALATION_PATTERNS = (
        r"(正在|马上|已经|准备|计划|打算).{0,16}(自杀|自残|伤害自己|结束自己|结束生命|结束痛苦|彻底结束|伤害他人|杀人)",
        r"(?:我|自己).{0,12}(?:准备|计划|打算).{0,16}(?:药|安眠药|农药|刀|绳子).{0,16}(?:结束自己|结束生命|自杀|自残|伤害自己|结束痛苦)",
        r"(自杀|自残|伤害自己|结束自己|结束生命|结束痛苦|彻底结束|伤害他人).{0,16}(工具|药物|刀|绳子|时间|地点|今晚|现在|马上)",
        r"(今晚|现在|马上|立刻).{0,16}(结束痛苦|彻底结束|不想活|撑不过去)",
        r"(我有|已经准备).{0,16}(刀|药|绳子|工具).{0,16}(伤害自己|自杀|自残)",
    )

    NON_SELF_CONTEXT_PATTERN = re.compile(
        r"新闻|报道|论文|作业|歌词|电影|小说|医学咨询|术语|朋友说|同学说|患者|来访者",
        re.IGNORECASE,
    )
    FIRST_PERSON_RISK_PATTERN = re.compile(
        r"(?:我|自己).{0,16}(?:想死|不想活|自杀|自残|伤害|计划|准备|打算|撑不住|结束)",
        re.IGNORECASE,
    )

    @classmethod
    def _redact_pii(cls, message: str) -> tuple[str, list[str]]:
        redacted = message
        pii_types: list[str] = []
        for pii_type, pattern in cls.PII_PATTERNS.items():
            if pattern.search(redacted):
                pii_types.append(pii_type)
                redacted = pattern.sub(f"[REDACTED_{pii_type.upper()}]", redacted)
        return redacted, pii_types

    @staticmethod
    def _matches(patterns: tuple[str, ...], message: str) -> bool:
        return any(re.search(pattern, message, re.IGNORECASE) for pattern in patterns)

    async def run(self, request: SafetyGateRequest, context: AgentContext) -> SafetyDecision:
        message = request.message.strip()
        redacted, pii_types = self._redact_pii(message)
        violations: list[str] = []
        evidence: list[str] = []

        injection_hit = self._matches(self.INJECTION_PATTERNS, message)
        if injection_hit:
            violations.append("prompt_injection")
            evidence.append("检测到试图修改系统指令、泄露提示词或绕过安全策略的表达")

        if pii_types:
            violations.append("pii_detected")
            evidence.append("检测到需要脱敏的个人信息")

        quoted_or_third_person = (
            self.NON_SELF_CONTEXT_PATTERN.search(message)
            and not self.FIRST_PERSON_RISK_PATTERN.search(message)
        )
        escalation_hit = self._matches(self.ESCALATION_PATTERNS, message) and not quoted_or_third_person
        if escalation_hit:
            return SafetyDecision(
                decision="escalate",
                redacted_message=redacted,
                violations=violations + ["immediate_safety_signal"],
                pii_types=pii_types,
                requires_human=True,
                evidence=evidence + ["检测到可能的即时安全风险，进入危机安全流程"],
            )

        if injection_hit:
            return SafetyDecision(
                decision="block",
                redacted_message=redacted,
                violations=violations,
                pii_types=pii_types,
                evidence=evidence,
            )

        if pii_types:
            return SafetyDecision(
                decision="redact",
                redacted_message=redacted,
                violations=violations,
                pii_types=pii_types,
                evidence=evidence,
            )

        return SafetyDecision(decision="allow", redacted_message=message)

    async def assess(self, message: str, context: AgentContext | None = None) -> SafetyDecision:
        return await self.run(
            SafetyGateRequest(message=message),
            context or AgentContext(),
        )
