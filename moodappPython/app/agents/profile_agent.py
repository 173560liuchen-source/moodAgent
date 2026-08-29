from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .crisis_agent import CrisisAnalysis
from .emotion_agent import EmotionAnalysis
from .rag_agent import RAGAnalysis
from ..schemas import ChatMessage, ModelChatResponse


ProfileCategory = Literal[
    "stress_source",
    "support_resource",
    "coping_method",
    "sleep_status",
    "study_status",
    "social_status",
    "communication_preference",
    "effective_advice",
]

ProfileOperation = Literal["add", "update", "delete", "no_change"]


class ProfilePatchItem(BaseModel):
    """单条画像变更建议。

    Python 只生成 patch，不直接持久化。Java 接收后负责用户查看、修改、删除和入库。
    """

    model_config = ConfigDict(extra="forbid")

    category: ProfileCategory
    value: str = Field(min_length=1, max_length=300)
    operation: ProfileOperation = "add"
    source: Literal[
        "current_message",
        "recent_history",
        "emotion_agent",
        "crisis_agent",
        "dialogue_agent",
        "rag_agent",
    ]
    evidence: str = Field(min_length=1, max_length=500)
    confidence: float = Field(ge=0.0, le=1.0)
    editable: bool = True
    deletable: bool = True
    sensitivity: Literal["normal", "sensitive", "safety_critical"] = "normal"


class ProfileControlPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_can_view: bool = True
    user_can_modify: bool = True
    user_can_delete: bool = True
    persistence_owner: Literal["java_backend"] = "java_backend"
    python_stores_full_chat: bool = False


class ProfileAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent: str = "profile"
    patch_items: list[ProfilePatchItem] = Field(default_factory=list)
    summary: str = ""
    confidence: float = Field(ge=0.0, le=1.0)
    control_policy: ProfileControlPolicy = Field(default_factory=ProfileControlPolicy)
    skipped_reasons: list[str] = Field(default_factory=list)
    prompt_version: str = "profile-agent-rules-6.4.0"


class ProfileAgent:
    """长期画像智能体。

    职责：
    - 从当前消息、近期历史和上游智能体结果中生成画像 patch；
    - 每条 patch 必须有来源、证据和置信度；
    - 不做人格诊断，不直接写数据库，不保存完整聊天；
    - 用户查看/修改/删除由 Java 后端实现。
    """

    name = "profile"
    version = "6.4.0"

    _category_keywords: tuple[tuple[ProfileCategory, tuple[str, ...], str], ...] = (
        ("sleep_status", ("睡不着", "失眠", "睡眠", "入睡", "早醒", "熬夜", "睡不好"), "睡眠状态"),
        ("study_status", ("学习", "考试", "作业", "课程", "绩点", "成绩", "复习"), "学习状态"),
        ("social_status", ("同学", "朋友", "室友", "宿舍", "人际", "孤独", "社交"), "社交状态"),
        ("support_resource", ("父母", "家人", "朋友", "老师", "辅导员", "心理中心", "同学"), "支持资源"),
        ("coping_method", ("深呼吸", "冥想", "运动", "散步", "听歌", "写日记", "放松"), "应对方式"),
        ("communication_preference", ("别说教", "简单点", "慢慢说", "直接说", "温柔", "陪我"), "沟通偏好"),
        ("effective_advice", ("有用", "有效", "好多了", "缓解", "舒服点", "管用"), "有效建议"),
    )

    _stress_patterns: tuple[re.Pattern[str], ...] = (
        re.compile(r"(.{0,20})(压力|焦虑|紧张|崩溃|烦)(.{0,20})"),
        re.compile(r"因为(.{1,40})(难受|压力|焦虑|睡不着)"),
        re.compile(r"(考试|学习|作业|成绩|人际|宿舍|家庭|经济|就业|实习).{0,20}(压力|焦虑|烦|难受)"),
    )

    def analyze(
        self,
        *,
        message: str,
        history: list[ChatMessage] | None = None,
        emotion: EmotionAnalysis | None = None,
        crisis: CrisisAnalysis | None = None,
        rag: RAGAnalysis | None = None,
        dialogue: ModelChatResponse | None = None,
        existing_profile: dict[str, Any] | None = None,
    ) -> ProfileAnalysis:
        clean_message = message.strip()
        items: list[ProfilePatchItem] = []
        skipped_reasons: list[str] = []

        if not clean_message:
            return ProfileAnalysis(
                patch_items=[],
                summary="未生成画像更新：当前消息为空。",
                confidence=0.0,
                skipped_reasons=["empty_message"],
            )

        items.extend(self._extract_from_message(clean_message))
        items.extend(self._extract_from_history(history or []))
        if emotion:
            items.extend(self._extract_from_emotion(emotion, clean_message))
        if crisis:
            items.extend(self._extract_from_crisis(crisis))
        if rag:
            items.extend(self._extract_from_rag(rag))
        if dialogue:
            items.extend(self._extract_from_dialogue(dialogue))

        deduplicated = self._deduplicate(items)
        if existing_profile:
            deduplicated = self._mark_operations(deduplicated, existing_profile)
        if not deduplicated:
            skipped_reasons.append("no_profile_signal_detected")

        return ProfileAnalysis(
            patch_items=deduplicated,
            summary=self._summary(deduplicated),
            confidence=self._overall_confidence(deduplicated),
            skipped_reasons=skipped_reasons,
        )

    def _extract_from_message(self, message: str) -> list[ProfilePatchItem]:
        items: list[ProfilePatchItem] = []

        for pattern in self._stress_patterns:
            match = pattern.search(message)
            if match:
                evidence = self._compact_evidence(match.group(0))
                items.append(
                    ProfilePatchItem(
                        category="stress_source",
                        value=self._normalize_value(evidence),
                        source="current_message",
                        evidence=evidence,
                        confidence=0.72,
                        sensitivity="sensitive",
                    )
                )
                break

        for category, keywords, label in self._category_keywords:
            hits = [keyword for keyword in keywords if keyword in message]
            if not hits:
                continue
            evidence = self._evidence_window(message, hits[0])
            items.append(
                ProfilePatchItem(
                    category=category,
                    value=f"{label}线索：{hits[0]}",
                    source="current_message",
                    evidence=evidence,
                    confidence=self._category_confidence(category),
                    sensitivity=self._category_sensitivity(category),
                )
            )
        return items

    def _extract_from_history(self, history: list[ChatMessage]) -> list[ProfilePatchItem]:
        items: list[ProfilePatchItem] = []
        for chat in history[-6:]:
            if chat.role != "user":
                continue
            content = chat.content.strip()
            if not content:
                continue
            matched_categories: set[ProfileCategory] = set()
            for category, keywords, label in self._category_keywords:
                if category in matched_categories:
                    continue
                hit = next((keyword for keyword in keywords if keyword in content), None)
                if not hit:
                    continue
                items.append(
                    ProfilePatchItem(
                        category=category,
                        value=f"{label}线索：{hit}",
                        source="recent_history",
                        evidence=self._evidence_window(content, hit),
                        confidence=max(0.35, self._category_confidence(category) - 0.15),
                        sensitivity=self._category_sensitivity(category),
                    )
                )
                matched_categories.add(category)
        return items

    @staticmethod
    def _extract_from_emotion(
        emotion: EmotionAnalysis,
        message: str,
    ) -> list[ProfilePatchItem]:
        items: list[ProfilePatchItem] = []
        if emotion.insufficient_data:
            return items
        dominant = max(
            (
                ("压力", emotion.stress),
                ("焦虑", emotion.anxiety),
                ("抑郁情绪线索", emotion.depression),
                ("孤独感", emotion.loneliness),
            ),
            key=lambda item: item[1],
        )
        if dominant[1] >= 0.65 and emotion.confidence >= 0.4:
            items.append(
                ProfilePatchItem(
                    category="stress_source",
                    value=f"近期{dominant[0]}较明显",
                    source="emotion_agent",
                    evidence=emotion.evidence[0] if emotion.evidence else message[:80],
                    confidence=round(min(0.85, emotion.confidence * dominant[1] + 0.2), 4),
                    sensitivity="sensitive",
                )
            )
        return items

    @staticmethod
    def _extract_from_crisis(crisis: CrisisAnalysis) -> list[ProfilePatchItem]:
        if crisis.level == "low" and not crisis.requires_human_review:
            return []
        value = (
            "需要安全支持和人工关注"
            if crisis.level == "high"
            else "近期需要持续观察和可信任支持"
        )
        return [
            ProfilePatchItem(
                category="support_resource",
                value=value,
                source="crisis_agent",
                evidence=crisis.evidence[0] if crisis.evidence else f"risk_level={crisis.level}",
                confidence=max(0.6, crisis.confidence),
                sensitivity="safety_critical" if crisis.level == "high" else "sensitive",
            )
        ]

    @staticmethod
    def _extract_from_rag(rag: RAGAnalysis) -> list[ProfilePatchItem]:
        if not rag.has_evidence or not rag.citations:
            return []
        categories = {citation.category for citation in rag.citations}
        items: list[ProfilePatchItem] = []
        if "sleep_management" in categories:
            items.append(
                ProfilePatchItem(
                    category="effective_advice",
                    value="可优先尝试低负担睡眠管理建议",
                    source="rag_agent",
                    evidence=rag.citations[0].chunk_id,
                    confidence=min(0.75, rag.confidence),
                )
            )
        if "stress_management" in categories:
            items.append(
                ProfilePatchItem(
                    category="effective_advice",
                    value="可优先尝试压力管理和任务拆解建议",
                    source="rag_agent",
                    evidence=rag.citations[0].chunk_id,
                    confidence=min(0.75, rag.confidence),
                )
            )
        return items

    @staticmethod
    def _extract_from_dialogue(dialogue: ModelChatResponse) -> list[ProfilePatchItem]:
        content = dialogue.content.strip()
        if not content:
            return []
        if any(word in content for word in ("深呼吸", "拆小", "放松", "睡眠", "联系")):
            return [
                ProfilePatchItem(
                    category="effective_advice",
                    value="本轮已提供低负担支持建议",
                    source="dialogue_agent",
                    evidence=content[:120],
                    confidence=0.45,
                )
            ]
        return []

    @staticmethod
    def _category_confidence(category: ProfileCategory) -> float:
        return {
            "stress_source": 0.72,
            "support_resource": 0.68,
            "coping_method": 0.7,
            "sleep_status": 0.78,
            "study_status": 0.76,
            "social_status": 0.7,
            "communication_preference": 0.75,
            "effective_advice": 0.58,
        }[category]

    @staticmethod
    def _category_sensitivity(category: ProfileCategory) -> Literal["normal", "sensitive", "safety_critical"]:
        if category in {"stress_source", "sleep_status", "social_status"}:
            return "sensitive"
        return "normal"

    @staticmethod
    def _compact_evidence(text: str) -> str:
        return re.sub(r"\s+", " ", text.strip())[:160]

    @staticmethod
    def _normalize_value(text: str) -> str:
        value = re.sub(r"\s+", " ", text.strip("，。,.；; "))
        return value[:120] or "压力相关线索"

    def _evidence_window(self, text: str, keyword: str) -> str:
        index = text.find(keyword)
        if index < 0:
            return self._compact_evidence(text[:120])
        start = max(0, index - 24)
        end = min(len(text), index + len(keyword) + 24)
        return self._compact_evidence(text[start:end])

    @staticmethod
    def _deduplicate(items: list[ProfilePatchItem]) -> list[ProfilePatchItem]:
        best: dict[tuple[str, str], ProfilePatchItem] = {}
        for item in items:
            key = (item.category, item.value)
            if key not in best or item.confidence > best[key].confidence:
                best[key] = item
        return sorted(
            best.values(),
            key=lambda item: (item.sensitivity == "safety_critical", item.confidence),
            reverse=True,
        )[:12]

    @staticmethod
    def _mark_operations(
        items: list[ProfilePatchItem],
        existing_profile: dict[str, Any],
    ) -> list[ProfilePatchItem]:
        marked: list[ProfilePatchItem] = []
        for item in items:
            existing_value = existing_profile.get(item.category)
            operation: ProfileOperation = "add"
            if existing_value:
                operation = "no_change" if str(existing_value) == item.value else "update"
            marked.append(item.model_copy(update={"operation": operation}))
        return marked

    @staticmethod
    def _summary(items: list[ProfilePatchItem]) -> str:
        if not items:
            return "未检测到足够稳定的画像更新线索。"
        categories = "、".join(sorted({item.category for item in items}))
        return f"生成 {len(items)} 条画像变更建议，涉及：{categories}。"

    @staticmethod
    def _overall_confidence(items: list[ProfilePatchItem]) -> float:
        if not items:
            return 0.0
        return round(sum(item.confidence for item in items) / len(items), 4)
