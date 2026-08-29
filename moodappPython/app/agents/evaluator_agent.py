from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .crisis_agent import CrisisAnalysis
from .rag_agent import RAGAnalysis
from .risk_agent import RiskAnalysis
from .safety_gate import SafetyDecision
from .trend_agent import TrendAnalysis
from .intervention_agent import InterventionAnalysis


class EvaluationIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: Literal[
        "diagnostic_language",
        "overpromise",
        "unsupported_reference",
        "missing_rag_citation",
        "rag_grounding_weak",
        "unsupported_recommendation",
        "citation_category_mismatch",
        "internal_reference_leak",
        "risk_style_mismatch",
        "blocked_content_leak",
        "empty_reply",
    ]
    severity: Literal["low", "medium", "high"]
    evidence: str = Field(min_length=1)
    fix_applied: bool = False


class EvaluationAnalysis(BaseModel):
    """最终回复评估结果。

    该结构用于审计和比赛答辩：每个问题都有证据，修正动作可追踪。
    """

    model_config = ConfigDict(extra="forbid")

    agent: str = "evaluator"
    passed: bool
    score: float = Field(ge=0.0, le=1.0)
    action: Literal["approve", "revise", "escalate"]
    issues: list[EvaluationIssue] = Field(default_factory=list)
    corrected_reply: str | None = None
    final_reply: str = Field(min_length=1)
    requires_human_review: bool = False
    checked_dimensions: list[str] = Field(default_factory=list)
    validated_rag_chunk_ids: list[str] = Field(default_factory=list)
    rag_grounding_score: float = Field(default=0.0, ge=0.0, le=1.0)
    prompt_version: str = "evaluator-agent-rules-7.1.0"


class EvaluatorAgent:
    """最终回复评估智能体。

    职责：
    - 检查回复是否安全；
    - 检查是否出现诊断或过度承诺；
    - 检查 RAG 引用是否真实来自检索结果；
    - 检查中高风险回复是否包含线下/人工支持；
    - 必要时做确定性修正，不能降低上游风险等级。
    """

    name = "evaluator"
    version = "7.1.0"

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
    _reference_line_pattern = re.compile(
        r"(?:参考(?:资料)?|引用|来源)\s*[：:].*",
        re.IGNORECASE,
    )
    _support_keywords = ("可信任的人", "学校心理中心", "急救", "危机热线", "不要独处")

    def evaluate(
        self,
        *,
        reply: str,
        crisis: CrisisAnalysis,
        safety: SafetyDecision,
        rag: RAGAnalysis | None = None,
        risk: RiskAnalysis | None = None,
        trend: TrendAnalysis | None = None,
        intervention: InterventionAnalysis | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EvaluationAnalysis:
        checked_dimensions = [
            "non_empty_reply",
            "safety_policy",
            "diagnostic_language",
            "overpromise",
            "rag_citation_integrity",
            "rag_grounding_coverage",
            "recommendation_evidence_consistency",
            "internal_reference_privacy",
            "risk_style_consistency",
            "risk_result_consistency",
            "intervention_alignment",
        ]
        issues: list[EvaluationIssue] = []
        final_reply = reply.strip()

        if not final_reply and not (rag and rag.has_evidence and rag.citations):
            final_reply = "我在这里。你可以先用一句话告诉我，现在最困扰你的是什么。"
            issues.append(
                EvaluationIssue(
                    code="empty_reply",
                    severity="high",
                    evidence="最终回复为空",
                    fix_applied=True,
                )
            )

        if safety.decision == "block" and final_reply not in {
            "这个请求无法处理。请换一种方式描述你的问题。",
        }:
            final_reply = "这个请求无法处理。请换一种方式描述你的问题。"
            issues.append(
                EvaluationIssue(
                    code="blocked_content_leak",
                    severity="high",
                    evidence="安全闸门已 block，但最终回复不是阻断模板",
                    fix_applied=True,
                )
            )

        final_reply, diagnosis_issues = self._replace_patterns(
            final_reply,
            self._diagnosis_patterns,
            code="diagnostic_language",
            severity="high",
        )
        issues.extend(diagnosis_issues)

        final_reply, promise_issues = self._replace_patterns(
            final_reply,
            self._overpromise_patterns,
            code="overpromise",
            severity="medium",
        )
        issues.extend(promise_issues)

        final_reply, reference_issues = self._validate_references(final_reply, rag)
        issues.extend(reference_issues)

        final_reply, recommendation_issues = self._validate_recommendations(final_reply, rag)
        issues.extend(recommendation_issues)

        final_reply, substantive_issue = self._ensure_substantive_rag_reply(final_reply, rag)
        if substantive_issue:
            issues.append(substantive_issue)

        final_reply, privacy_issues = self._remove_internal_references(final_reply, rag)
        issues.extend(privacy_issues)

        if rag and rag.has_evidence and rag.selected_categories and not rag.category_fallback_used:
            unexpected = sorted({
                citation.category for citation in rag.citations
                if citation.category not in rag.selected_categories
            })
            if unexpected:
                issues.append(EvaluationIssue(
                    code="citation_category_mismatch",
                    severity="medium",
                    evidence="引用类别不在本次分类结果中：" + "、".join(unexpected),
                    fix_applied=False,
                ))

        validated_rag_chunk_ids = self._validated_rag_chunk_ids(final_reply, rag)
        rag_grounding_score = self._rag_grounding_score(final_reply, rag, validated_rag_chunk_ids)
        if rag and rag.has_evidence and rag.citations and rag_grounding_score < 0.5:
            issues.append(
                EvaluationIssue(
                    code="rag_grounding_weak",
                    severity="medium",
                    evidence="RAG 返回了可引用资料，但最终回复与检索证据的内容或资料标题对应不足。",
                    fix_applied=False,
                )
            )

        final_reply, risk_issue = self._ensure_risk_style(final_reply, crisis, risk)
        if risk_issue:
            issues.append(risk_issue)

        score = self._score(issues)
        requires_human_review = bool(
            crisis.requires_human_review
            or (risk and risk.requires_human_review)
            or (intervention and intervention.requires_human_review)
            or crisis.level in {"medium", "high"}
            or (risk and risk.risk_level in {"medium", "high"})
            # Text-quality issues that were deterministically repaired do not
            # represent an unresolved clinical risk. Escalate only when a
            # high-severity evaluator issue remains unfixed; upstream crisis,
            # risk, and intervention decisions still take precedence above.
            or any(
                issue.severity == "high" and not issue.fix_applied
                for issue in issues
            )
        )
        action: Literal["approve", "revise", "escalate"]
        if (
            crisis.level == "high"
            or crisis.action == "crisis_response"
            or (risk and risk.risk_level == "high")
        ):
            action = "escalate"
        elif issues:
            action = "revise"
        else:
            action = "approve"

        return EvaluationAnalysis(
            passed=not issues,
            score=score,
            action=action,
            issues=issues,
            corrected_reply=final_reply if final_reply != reply.strip() else None,
            final_reply=final_reply,
            requires_human_review=requires_human_review,
            checked_dimensions=checked_dimensions,
            validated_rag_chunk_ids=validated_rag_chunk_ids,
            rag_grounding_score=rag_grounding_score,
        )

    @staticmethod
    def _replace_patterns(
        text: str,
        patterns: tuple[tuple[re.Pattern[str], str], ...],
        *,
        code: Literal["diagnostic_language", "overpromise"],
        severity: Literal["medium", "high"],
    ) -> tuple[str, list[EvaluationIssue]]:
        issues: list[EvaluationIssue] = []
        repaired = text
        for pattern, replacement in patterns:
            match = pattern.search(repaired)
            if not match:
                continue
            evidence = match.group(0)
            repaired = pattern.sub(replacement, repaired)
            issues.append(
                EvaluationIssue(
                    code=code,
                    severity=severity,
                    evidence=evidence,
                    fix_applied=True,
                )
            )
        return repaired, issues

    @staticmethod
    def _remove_internal_references(
        text: str,
        rag: RAGAnalysis | None,
    ) -> tuple[str, list[EvaluationIssue]]:
        repaired = text
        evidence: list[str] = []
        for citation in (rag.citations if rag else []):
            if citation.file_path and citation.file_path in repaired:
                repaired = repaired.replace(citation.file_path, "")
                evidence.append(citation.file_path)
        internal_path = re.compile(r"(?i)(?:file_path\s*[:=]\s*)?(?:[a-z]:\\[^\s，。；]+|/(?:home|app|workspace|srv|var)/[^\s，。；]+)")
        matches = [match.group(0) for match in internal_path.finditer(repaired)]
        if matches:
            repaired = internal_path.sub("", repaired)
            evidence.extend(matches)
        repaired = re.sub(r"[ \t]+([。！？；;，,])", r"\1", repaired)
        repaired = re.sub(r"[ \t]{2,}", " ", repaired).strip()
        if not evidence:
            return repaired, []
        return repaired, [EvaluationIssue(
            code="internal_reference_leak",
            severity="high",
            evidence="；".join(evidence[:3]),
            fix_applied=True,
        )]

    def _validate_references(
        self,
        text: str,
        rag: RAGAnalysis | None,
    ) -> tuple[str, list[EvaluationIssue]]:
        issues: list[EvaluationIssue] = []
        citations = list(rag.citations if rag and rag.has_evidence else [])

        lines: list[str] = []
        changed = False
        for line in text.splitlines():
            match = self._reference_line_pattern.search(line)
            if not match:
                lines.append(line)
                continue

            if not citations:
                changed = True
                issues.append(
                    EvaluationIssue(
                        code="unsupported_reference",
                        severity="high",
                        evidence=line.strip(),
                        fix_applied=True,
                    )
                )
                cleaned = self._reference_line_pattern.sub("", line).strip()
                if cleaned:
                    lines.append(cleaned)
                continue

            # Citation data belongs to structured RAG/audit fields, not chat.
            changed = True
            cleaned = self._reference_line_pattern.sub("", line).strip()
            if cleaned:
                lines.append(cleaned)

        repaired = "\n".join(line for line in lines if line.strip()).strip() if changed else text.strip()
        if citations:
            had_internal_identifiers = any(
                identifier and identifier in text
                for citation in citations
                for identifier in (citation.document_id, citation.chunk_id)
            )
            for citation in citations:
                labels = {citation.title.strip(), citation.source.strip()}
                identifiers = {citation.document_id.strip(), citation.chunk_id.strip()}
                for label in filter(None, labels):
                    for identifier in filter(None, identifiers):
                        repaired = re.sub(
                            rf"\s*{re.escape(label)}\s*/\s*{re.escape(identifier)}",
                            "",
                            repaired,
                            flags=re.IGNORECASE,
                        )
                for identifier in filter(None, identifiers):
                    repaired = re.sub(
                        rf"\s*/?\s*{re.escape(identifier)}",
                        "",
                        repaired,
                        flags=re.IGNORECASE,
                    )

            if had_internal_identifiers:
                issues.append(
                    EvaluationIssue(
                        code="internal_reference_leak",
                        severity="high",
                        evidence="用户回复中的内部引用标识已移除，溯源信息仅保留在结构化审计字段",
                        fix_applied=True,
                    )
                )
        elif changed:
            issues.append(
                EvaluationIssue(
                    code="unsupported_reference",
                    severity="high",
                    evidence="未提供 RAG 证据，已移除用户回复中的来源声明",
                    fix_applied=True,
                )
            )
        return repaired.strip(), issues

    def _ensure_risk_style(
        self,
        text: str,
        crisis: CrisisAnalysis,
        risk: RiskAnalysis | None = None,
    ) -> tuple[str, EvaluationIssue | None]:
        risk_level = risk.risk_level if risk else crisis.level
        requires_human = bool(
            crisis.requires_human_review or (risk and risk.requires_human_review)
        )
        if risk_level not in {"medium", "high"} and not requires_human:
            return text, None
        if any(keyword in text for keyword in self._support_keywords):
            return text, None

        if risk_level == "high" or crisis.action == "crisis_response":
            addition = (
                "请优先保证安全：尽量不要独处，立即联系身边可信任的人，"
                "必要时联系学校心理中心、当地急救或危机热线。"
            )
        else:
            addition = (
                "如果这种状态持续或加重，建议你联系一位可信任的人，"
                "也可以预约学校心理中心获得线下支持。"
            )
        return (
            f"{text.rstrip()}\n\n{addition}",
            EvaluationIssue(
                code="risk_style_mismatch",
                severity="high" if risk_level == "high" else "medium",
                evidence=f"risk_level={risk_level}, requires_human_review={requires_human}",
                fix_applied=True,
            ),
        )

    @classmethod
    def _validate_recommendations(
        cls,
        text: str,
        rag: RAGAnalysis | None,
    ) -> tuple[str, list[EvaluationIssue]]:
        """有 RAG 证据时，建议句必须与至少一条真实知识块有词项支撑。"""
        if not rag or not rag.has_evidence or not rag.citations:
            return text, []
        recommendation_markers = ("建议", "可以", "最好", "尽量", "不妨", "需要", "应当", "记得")
        preserved: list[str] = []
        issues: list[EvaluationIssue] = []
        for sentence in re.split(r"(?<=[。！？!?])|\n+", text):
            candidate = sentence.strip()
            if not candidate:
                continue
            if not any(marker in candidate for marker in recommendation_markers):
                preserved.append(candidate)
                continue
            support = max(cls._content_overlap(candidate, citation.content) for citation in rag.citations)
            if support >= 0.12:
                preserved.append(candidate)
                continue
            issues.append(EvaluationIssue(
                code="unsupported_recommendation",
                severity="medium",
                evidence=candidate[:300],
                fix_applied=True,
            ))
        repaired = "".join(preserved).strip()
        # Leave an empty result to the category-aware RAG repair below. A generic
        # sentence would look non-empty and prevent recovery of useful content.
        return repaired, issues

    @staticmethod
    def _ensure_substantive_rag_reply(
        text: str,
        rag: RAGAnalysis | None,
    ) -> tuple[str, EvaluationIssue | None]:
        """A user-facing RAG answer must never be empty after evidence checks."""
        if not rag or not rag.has_evidence or not rag.citations:
            return text, None
        body = re.sub(
            r"(?is)\s*(?:参考(?:资料)?|引用|来源)\s*[：:].*$",
            "",
            text,
        ).strip()
        if len(body) >= 12:
            return text, None

        categories = {citation.category for citation in rag.citations}
        if "sleep_management" in categories:
            minimum_reply = (
                "可以先从一个低负担步骤开始：固定起床时间，并在睡前减少刷手机、刷题等高刺激内容。"
                "连续记录一到两周的入睡时间和白天状态；如果仍明显影响生活，再联系学校心理中心或专业人员。"
            )
        elif "school_resources" in categories:
            minimum_reply = (
                "可以先通过学校官网、公众号、线上预约系统或现场服务台查询心理中心的预约方式；"
                "预约时简要说明当前困扰、持续时间以及对学习生活的影响即可。"
            )
        elif "stress_management" in categories:
            minimum_reply = (
                "可以先把当前任务缩小成一个十分钟内能完成的步骤，完成后短暂休息并重新排序剩余任务。"
                "如果压力持续影响睡眠或上课，再考虑联系学校心理中心获得进一步支持。"
            )
        else:
            minimum_reply = (
                "现有资料支持先选择一个低负担、可以立即执行的小步骤，并观察它对学习和生活状态的影响。"
                "资料没有覆盖的部分不作确定性判断。"
            )

        return minimum_reply, EvaluationIssue(
            code="empty_reply",
            severity="high",
            evidence="RAG 建议校验后正文为空或过短，已使用检索类别对应的最小可信回答",
            fix_applied=True,
        )

    @staticmethod
    def _score(issues: list[EvaluationIssue]) -> float:
        if not issues:
            return 1.0
        penalty = 0.0
        for issue in issues:
            if issue.severity == "high":
                penalty += 0.35
            elif issue.severity == "medium":
                penalty += 0.2
            else:
                penalty += 0.1
        return round(max(0.0, 1.0 - penalty), 4)

    @staticmethod
    def _validated_rag_chunk_ids(
        text: str,
        rag: RAGAnalysis | None,
    ) -> list[str]:
        if not rag or not rag.has_evidence:
            return []
        return [
            citation.chunk_id
            for citation in rag.citations
            if citation.chunk_id
            and (
                citation.title in text
                or citation.source in text
                or EvaluatorAgent._content_overlap(text, citation.content) >= 0.12
            )
        ]

    @staticmethod
    def _rag_grounding_score(
        text: str,
        rag: RAGAnalysis | None,
        validated_chunk_ids: list[str],
    ) -> float:
        if not rag or not rag.has_evidence or not rag.citations:
            return 1.0
        cited = [citation for citation in rag.citations if citation.chunk_id in validated_chunk_ids]
        if not cited:
            return 0.0
        title_hits = sum(
            1 for citation in cited
            if citation.source in text or (citation.title and citation.title in text)
        )
        support_scores = [EvaluatorAgent._content_overlap(text, citation.content) for citation in cited]
        evidence_coverage = len(cited) / max(1, len(rag.citations))
        title_coverage = title_hits / max(1, len(cited))
        content_support = sum(support_scores) / max(1, len(support_scores))
        return round(min(1.0, 0.35 * evidence_coverage + 0.20 * title_coverage + 0.45 * content_support), 4)

    @staticmethod
    def _content_overlap(reply: str, excerpt: str) -> float:
        """Conservative lexical support check; model-based entailment belongs in offline evaluation."""

        def terms(value: str) -> set[str]:
            ascii_terms = set(re.findall(r"[A-Za-z0-9_-]{2,}", value.lower()))
            chinese_runs = re.findall(r"[\u4e00-\u9fff]{2,}", value)
            chinese_bigrams = {
                run[index:index + 2]
                for run in chinese_runs
                for index in range(len(run) - 1)
            }
            return ascii_terms | chinese_bigrams

        evidence_terms = terms(excerpt)
        if not evidence_terms:
            return 0.0
        overlap = len(evidence_terms & terms(reply))
        return min(1.0, overlap / min(12, max(3, len(evidence_terms))))
