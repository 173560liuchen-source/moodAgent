from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .emotion_agent import EmotionAnalysis
from .risk_agent import RiskAnalysis
from .trend_agent import TrendAnalysis


class FollowUpAnalysis(BaseModel):
    """对已有干预方案的执行与效果做可审计判断。"""

    model_config = ConfigDict(extra="forbid")

    agent: str = "follow_up"
    plan_id: str | None = None
    adherence: Literal["completed", "partial", "not_started", "unknown"]
    effectiveness: Literal["improved", "unchanged", "worsened", "insufficient_data"]
    decision: Literal["keep", "adjust", "replace", "escalate"]
    target_action_ids: list[str] = Field(default_factory=list)
    decision_scope: Literal["action", "plan", "safety"] = "plan"
    evidence: list[str] = Field(default_factory=list)
    emotion_change: str = "insufficient_data"
    risk_change: str = "stable"
    adjustment_reason: str = ""
    confidence: float = Field(ge=0.0, le=1.0)
    prompt_version: str = "follow-up-rules-1.0.0"


@dataclass(frozen=True)
class _FeedbackSignal:
    """将页面和文本两种入口归一为同一种决策输入。"""

    adherence: Literal["completed", "partial", "not_started", "unknown"]
    effectiveness: Literal["improved", "unchanged", "worsened", "insufficient_data"]
    burden_high: bool
    target_action_ids: list[str]
    evidence: list[str]
    confidence: float


class FollowUpAgent:
    name = "follow_up"
    version = "1.0.0"

    _NOT_STARTED = ("没做", "没有做", "没来得及", "太忙", "忘了", "没坚持")
    _PARTIAL = ("偶尔", "有时", "断断续续", "只做了", "部分")
    _IMPROVED = ("好一点", "好些", "缓解", "改善", "有用", "有效")
    _WORSENED = ("更糟", "加重", "恶化", "更严重")
    _UNCHANGED = ("没改善", "没效果", "还是", "没有变化", "不管用")

    def assess(
        self,
        *,
        message: str,
        latest_intervention: dict[str, Any] | None,
        action_feedbacks: list[dict[str, Any]] | None,
        trend: TrendAnalysis | None,
        emotion: EmotionAnalysis | None,
        risk: RiskAnalysis | None,
    ) -> FollowUpAnalysis:
        signal = self._signal_from_action_feedbacks(action_feedbacks or []) or self._signal_from_text(message)
        decision, reason = self._decide(signal)
        scope: Literal["action", "plan", "safety"] = "action" if signal.target_action_ids else "plan"
        if risk and risk.risk_level in {"medium", "high"}:
            decision, reason = "escalate", "风险评估提示需要升级人工关注。"
            scope = "safety"
        elif decision == "escalate":
            scope = "safety"
        return self._build_result(
            latest_intervention, signal.adherence, signal.effectiveness, decision, signal.evidence, trend, risk, reason,
            signal.confidence, signal.target_action_ids, scope,
        )

    @staticmethod
    def _decide(signal: _FeedbackSignal) -> tuple[Literal["keep", "adjust", "replace", "escalate"], str]:
        """唯一的四类跟进决策入口；页面与文本反馈共享此规则。"""
        if signal.effectiveness == "worsened":
            return "escalate", "用户反馈状态加重，需要升级关注与安全核查。"
        if signal.effectiveness == "unchanged" and signal.adherence == "completed":
            return "replace", "行动已完成但效果未改善，替换为不同类型的干预策略。"
        if signal.effectiveness == "improved" and signal.adherence == "completed":
            return "keep", "用户已完成行动并反馈有改善，保留并巩固有效做法。"
        if signal.adherence in {"not_started", "partial"} or signal.burden_high:
            return "adjust", "行动未充分执行或执行负担较高，先降低难度再评估效果。"
        return "adjust", "缺少明确效果反馈，先低负担调整并继续观察。"

    @staticmethod
    def _build_result(
        latest_intervention: dict[str, Any] | None,
        adherence: str,
        effectiveness: str,
        decision: str,
        evidence: list[str],
        trend: TrendAnalysis | None,
        risk: RiskAnalysis | None,
        reason: str,
        confidence: float,
        target_action_ids: list[str],
        decision_scope: Literal["action", "plan", "safety"],
    ) -> FollowUpAnalysis:
        plan_id = str(latest_intervention.get("id")) if latest_intervention and latest_intervention.get("id") is not None else None
        trend_change = (
            trend.intervention_comparison.interpretation
            if trend and trend.intervention_comparison.available
            else "insufficient_data"
        )
        return FollowUpAnalysis(
            plan_id=plan_id, adherence=adherence, effectiveness=effectiveness,
            target_action_ids=target_action_ids, decision_scope=decision_scope,
            decision=decision, evidence=evidence, emotion_change=trend_change,
            risk_change="elevated" if risk and risk.risk_level in {"medium", "high"} else "stable",
            adjustment_reason=reason, confidence=confidence,
        )

    @staticmethod
    def _signal_from_action_feedbacks(
        feedbacks: list[dict[str, Any]],
    ) -> _FeedbackSignal | None:
        """优先使用页面提交的动作级反馈，文本关键词只作为兼容回退。"""
        if not feedbacks:
            return None
        latest_by_action: dict[str, dict[str, Any]] = {}
        for item in feedbacks:
            action_id = str(item.get("actionId") or item.get("action_id") or "")
            if action_id and action_id not in latest_by_action:
                latest_by_action[action_id] = item
        records = list(latest_by_action.values())
        if not records:
            return None
        execution = [str(item.get("executionStatus") or item.get("execution_status") or "") for item in records]
        outcomes = [str(item.get("outcomeStatus") or item.get("outcome_status") or "") for item in records]
        difficulties = [item.get("difficulty") for item in records if item.get("difficulty") is not None]
        evidence = [
            f"动作反馈 {item.get('actionId') or item.get('action_id')}："
            f"执行={item.get('executionStatus') or item.get('execution_status')}，"
            f"效果={item.get('outcomeStatus') or item.get('outcome_status')}"
            for item in records[:5]
        ]
        if "worsened" in outcomes:
            targets = [str(item.get("actionId") or item.get("action_id")) for item in records if str(item.get("outcomeStatus") or item.get("outcome_status")) == "worsened"]
            return _FeedbackSignal("completed", "worsened", False, targets, evidence, 0.93)
        if "unchanged" in outcomes and "completed" in execution:
            targets = [str(item.get("actionId") or item.get("action_id")) for item in records if str(item.get("executionStatus") or item.get("execution_status")) == "completed" and str(item.get("outcomeStatus") or item.get("outcome_status")) == "unchanged"]
            return _FeedbackSignal("completed", "unchanged", False, targets, evidence, 0.90)
        if "improved" in outcomes and "completed" in execution:
            targets = [str(item.get("actionId") or item.get("action_id")) for item in records if str(item.get("executionStatus") or item.get("execution_status")) == "completed" and str(item.get("outcomeStatus") or item.get("outcome_status")) == "improved"]
            return _FeedbackSignal("completed", "improved", False, targets, evidence, 0.90)
        high_difficulty = any(isinstance(value, (int, float)) and value >= 4 for value in difficulties)
        if "not_started" in execution or "partial" in execution or high_difficulty:
            adherence = "not_started" if "not_started" in execution else "partial" if "partial" in execution else "completed"
            targets = [str(item.get("actionId") or item.get("action_id")) for item in records if str(item.get("executionStatus") or item.get("execution_status")) in {"not_started", "partial"} or isinstance(item.get("difficulty"), (int, float)) and item.get("difficulty") >= 4]
            return _FeedbackSignal(adherence, "insufficient_data", high_difficulty, targets, evidence, 0.88)
        return _FeedbackSignal("unknown", "insufficient_data", False, [], evidence, 0.75)

    def _signal_from_text(self, message: str) -> _FeedbackSignal:
        text = message.lower()
        evidence = ["存在历史正式干预方案", f"用户反馈：{message[:160]}"]
        if any(term in text for term in self._NOT_STARTED):
            return _FeedbackSignal("not_started", "insufficient_data", False, [], evidence, 0.65)
        if any(term in text for term in self._PARTIAL):
            return _FeedbackSignal("partial", "insufficient_data", False, [], evidence, 0.65)
        if any(term in text for term in self._WORSENED):
            return _FeedbackSignal("completed", "worsened", False, [], evidence, 0.82)
        if any(term in text for term in self._IMPROVED):
            return _FeedbackSignal("completed", "improved", False, [], evidence, 0.82)
        if any(term in text for term in self._UNCHANGED):
            return _FeedbackSignal("completed", "unchanged", False, [], evidence, 0.82)
        return _FeedbackSignal("completed", "insufficient_data", False, [], evidence, 0.65)
