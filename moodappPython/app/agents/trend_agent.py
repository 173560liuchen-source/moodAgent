from __future__ import annotations

from datetime import datetime, timedelta, timezone
from statistics import pstdev
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


TrendDirection = Literal["improving", "stable", "worsening", "insufficient_data"]


class EmotionPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timestamp: str
    anxiety: float = Field(ge=0.0, le=1.0)
    stress: float = Field(ge=0.0, le=1.0)
    depression: float = Field(ge=0.0, le=1.0)
    intervention: bool = False
    intervention_type: str | None = None


class MetricTrendDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric: Literal["stress", "anxiety", "depression"]
    trend: TrendDirection
    average: float = Field(ge=0.0, le=1.0)
    delta: float = Field(ge=-1.0, le=1.0)
    volatility: float = Field(ge=0.0, le=1.0)
    start_value: float = Field(ge=0.0, le=1.0)
    end_value: float = Field(ge=0.0, le=1.0)
    data_points: int = Field(ge=0)


class TrendWindowSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    window_days: int
    data_points: int = Field(ge=0)
    stress: MetricTrendDetail | None = None
    anxiety: MetricTrendDetail | None = None
    depression: MetricTrendDetail | None = None
    evidence: list[str] = Field(default_factory=list)
    insufficient_reasons: list[str] = Field(default_factory=list)


class RiskRecurrence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recurrence_detected: bool = False
    high_risk_episode_count: int = Field(default=0, ge=0)
    threshold: float = Field(default=0.75, ge=0.0, le=1.0)
    evidence: list[str] = Field(default_factory=list)


class InterventionComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")

    available: bool = False
    before_average_stress: float | None = Field(default=None, ge=0.0, le=1.0)
    after_average_stress: float | None = Field(default=None, ge=0.0, le=1.0)
    stress_delta_after_intervention: float | None = Field(default=None, ge=-1.0, le=1.0)
    interpretation: Literal["improved", "worsened", "stable", "insufficient_data"] = "insufficient_data"
    evidence: list[str] = Field(default_factory=list)


class TrendCalculationItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    formula: str
    value: float | str | bool
    evidence: list[str] = Field(default_factory=list)


class TrendAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data_points: int
    stress_trend: TrendDirection
    anxiety_trend: TrendDirection
    depression_trend: TrendDirection
    stress_average: float = 0.0
    stress_delta: float = 0.0
    consecutive_rise: int = 0
    confidence: float = 0.0
    evidence: list[str] = Field(default_factory=list)
    window_7d: TrendWindowSummary | None = None
    window_30d: TrendWindowSummary | None = None
    recurrence: RiskRecurrence = Field(default_factory=RiskRecurrence)
    intervention_comparison: InterventionComparison = Field(default_factory=InterventionComparison)
    calculation_trace: list[TrendCalculationItem] = Field(default_factory=list)
    insufficient_reasons: list[str] = Field(default_factory=list)
    prompt_version: str = "trend-agent-rules-4.5.0"


class TrendAgent:
    """基于结构化情绪历史进行 7 天、30 天和干预前后趋势分析。"""

    name = "trend"
    version = "4.5.0"
    HIGH_RISK_THRESHOLD = 0.75

    @staticmethod
    def _parse_timestamp(value: str) -> datetime | None:
        text = value.strip()
        if not text:
            return None
        try:
            normalized = text.replace("Z", "+00:00")
            parsed = datetime.fromisoformat(normalized)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            return None

    @classmethod
    def _sorted_points(cls, points: list[EmotionPoint]) -> list[tuple[EmotionPoint, datetime]]:
        parsed: list[tuple[EmotionPoint, datetime]] = []
        for point in points:
            timestamp = cls._parse_timestamp(point.timestamp)
            if timestamp is not None:
                parsed.append((point, timestamp))
        return sorted(parsed, key=lambda item: item[1])

    @staticmethod
    def _direction(values: list[float]) -> TrendDirection:
        if len(values) < 2:
            return "insufficient_data"
        delta = values[-1] - values[0]
        if delta >= 0.1:
            return "worsening"
        if delta <= -0.1:
            return "improving"
        return "stable"

    @staticmethod
    def _metric_detail(metric: Literal["stress", "anxiety", "depression"], values: list[float]) -> MetricTrendDetail:
        if not values:
            return MetricTrendDetail(
                metric=metric,
                trend="insufficient_data",
                average=0.0,
                delta=0.0,
                volatility=0.0,
                start_value=0.0,
                end_value=0.0,
                data_points=0,
            )
        delta = values[-1] - values[0] if len(values) >= 2 else 0.0
        return MetricTrendDetail(
            metric=metric,
            trend=TrendAgent._direction(values),
            average=round(sum(values) / len(values), 4),
            delta=round(delta, 4),
            volatility=round(pstdev(values), 4) if len(values) >= 2 else 0.0,
            start_value=round(values[0], 4),
            end_value=round(values[-1], 4),
            data_points=len(values),
        )

    @classmethod
    def _window_summary(
        cls,
        parsed_points: list[tuple[EmotionPoint, datetime]],
        *,
        window_days: int,
    ) -> TrendWindowSummary:
        if not parsed_points:
            return TrendWindowSummary(
                window_days=window_days,
                data_points=0,
                insufficient_reasons=["没有可解析时间戳的情绪数据"],
            )

        end_time = parsed_points[-1][1]
        start_time = end_time - timedelta(days=window_days)
        window = [point for point, timestamp in parsed_points if timestamp >= start_time]
        evidence = [f"{window_days}天窗口内共{len(window)}个时间点"]
        insufficient: list[str] = []
        if len(window) < 2:
            insufficient.append(f"{window_days}天窗口少于2个时间点，无法判断趋势方向")

        stress = [point.stress for point in window]
        anxiety = [point.anxiety for point in window]
        depression = [point.depression for point in window]

        stress_detail = cls._metric_detail("stress", stress)
        anxiety_detail = cls._metric_detail("anxiety", anxiety)
        depression_detail = cls._metric_detail("depression", depression)

        for label, detail in (("压力", stress_detail), ("焦虑", anxiety_detail), ("抑郁倾向", depression_detail)):
            if detail.trend != "insufficient_data":
                evidence.append(f"{label}{window_days}天趋势为{detail.trend}，变化{detail.delta:+.2f}")

        return TrendWindowSummary(
            window_days=window_days,
            data_points=len(window),
            stress=stress_detail,
            anxiety=anxiety_detail,
            depression=depression_detail,
            evidence=evidence,
            insufficient_reasons=insufficient,
        )

    @staticmethod
    def _consecutive_rise(values: list[float]) -> int:
        consecutive = 0
        for previous, current in zip(reversed(values[:-1]), reversed(values[1:])):
            if current > previous:
                consecutive += 1
            else:
                break
        return consecutive

    @classmethod
    def _recurrence(cls, points: list[EmotionPoint]) -> RiskRecurrence:
        episodes = 0
        in_episode = False
        for point in points:
            high = max(point.stress, point.anxiety, point.depression) >= cls.HIGH_RISK_THRESHOLD
            if high and not in_episode:
                episodes += 1
                in_episode = True
            elif not high:
                in_episode = False
        evidence = []
        if episodes:
            evidence.append(f"检测到{episodes}段高风险情绪波动区间")
        return RiskRecurrence(
            recurrence_detected=episodes >= 2,
            high_risk_episode_count=episodes,
            threshold=cls.HIGH_RISK_THRESHOLD,
            evidence=evidence,
        )

    @staticmethod
    def _average(values: list[float]) -> float | None:
        if not values:
            return None
        return round(sum(values) / len(values), 4)

    @classmethod
    def _intervention_comparison(cls, parsed_points: list[tuple[EmotionPoint, datetime]]) -> InterventionComparison:
        intervention_indexes = [index for index, (point, _) in enumerate(parsed_points) if point.intervention]
        if not intervention_indexes:
            return InterventionComparison(
                available=False,
                evidence=["没有干预标记，无法进行干预前后对比"],
            )
        index = intervention_indexes[-1]
        before = [point.stress for point, _ in parsed_points[max(0, index - 3):index]]
        after = [point.stress for point, _ in parsed_points[index + 1:index + 4]]
        before_avg = cls._average(before)
        after_avg = cls._average(after)
        if before_avg is None or after_avg is None:
            return InterventionComparison(
                available=False,
                before_average_stress=before_avg,
                after_average_stress=after_avg,
                evidence=["干预前或干预后数据不足，无法比较"],
            )
        delta = round(after_avg - before_avg, 4)
        if delta <= -0.1:
            interpretation: Literal["improved", "worsened", "stable", "insufficient_data"] = "improved"
        elif delta >= 0.1:
            interpretation = "worsened"
        else:
            interpretation = "stable"
        return InterventionComparison(
            available=True,
            before_average_stress=before_avg,
            after_average_stress=after_avg,
            stress_delta_after_intervention=delta,
            interpretation=interpretation,
            evidence=[f"干预后压力均值变化{delta:+.2f}"],
        )

    @staticmethod
    def _confidence(valid_points: int, insufficient_count: int) -> float:
        confidence = min(0.95, 0.4 + valid_points * 0.05)
        confidence -= min(0.25, insufficient_count * 0.05)
        return max(0.0, round(confidence, 4))

    def analyze(self, points: list[EmotionPoint]) -> TrendAnalysis:
        if not points:
            return TrendAnalysis(
                data_points=0,
                stress_trend="insufficient_data",
                anxiety_trend="insufficient_data",
                depression_trend="insufficient_data",
                evidence=["没有可用的历史情绪数据"],
                insufficient_reasons=["points为空"],
                calculation_trace=[
                    TrendCalculationItem(
                        name="data_availability",
                        formula="len(points)",
                        value=0,
                        evidence=["没有可用的历史情绪数据"],
                    )
                ],
            )

        parsed_points = self._sorted_points(points)
        if not parsed_points:
            return TrendAnalysis(
                data_points=len(points),
                stress_trend="insufficient_data",
                anxiety_trend="insufficient_data",
                depression_trend="insufficient_data",
                evidence=["没有可解析时间戳的历史情绪数据"],
                insufficient_reasons=["所有timestamp均无法解析"],
            )

        ordered_points = [point for point, _ in parsed_points]
        stress = [point.stress for point in ordered_points]
        anxiety = [point.anxiety for point in ordered_points]
        depression = [point.depression for point in ordered_points]

        stress_detail = self._metric_detail("stress", stress)
        anxiety_detail = self._metric_detail("anxiety", anxiety)
        depression_detail = self._metric_detail("depression", depression)
        consecutive_rise = self._consecutive_rise(stress)
        window_7d = self._window_summary(parsed_points, window_days=7)
        window_30d = self._window_summary(parsed_points, window_days=30)
        recurrence = self._recurrence(ordered_points)
        intervention_comparison = self._intervention_comparison(parsed_points)

        evidence = [f"共分析{len(parsed_points)}个有效时间点"]
        if len(parsed_points) != len(points):
            evidence.append(f"忽略{len(points) - len(parsed_points)}个无法解析时间戳的点")
        if consecutive_rise >= 2:
            evidence.append(f"压力连续上升{consecutive_rise}次")
        if abs(stress_detail.delta) >= 0.1:
            evidence.append(f"压力整体变化幅度为{stress_detail.delta:+.2f}")
        evidence.extend(window_7d.evidence[:3])
        evidence.extend(window_30d.evidence[:3])
        evidence.extend(recurrence.evidence)
        evidence.extend(intervention_comparison.evidence)

        insufficient_reasons = (
            window_7d.insufficient_reasons
            + window_30d.insufficient_reasons
            + ([] if intervention_comparison.available else intervention_comparison.evidence)
        )

        calculation_trace = [
            TrendCalculationItem(
                name="overall_stress_delta",
                formula="last_stress - first_stress",
                value=round(stress_detail.delta, 4),
                evidence=[f"{stress[0]:.2f} -> {stress[-1]:.2f}"],
            ),
            TrendCalculationItem(
                name="consecutive_rise",
                formula="count trailing pairs where current_stress > previous_stress",
                value=consecutive_rise,
                evidence=[f"压力连续上升{consecutive_rise}次"],
            ),
            TrendCalculationItem(
                name="risk_recurrence",
                formula="count high-risk episodes where max(stress, anxiety, depression) >= 0.75",
                value=recurrence.recurrence_detected,
                evidence=recurrence.evidence,
            ),
        ]

        return TrendAnalysis(
            data_points=len(parsed_points),
            stress_trend=stress_detail.trend,
            anxiety_trend=anxiety_detail.trend,
            depression_trend=depression_detail.trend,
            stress_average=stress_detail.average,
            stress_delta=stress_detail.delta,
            consecutive_rise=consecutive_rise,
            confidence=self._confidence(len(parsed_points), len(insufficient_reasons)),
            evidence=list(dict.fromkeys(evidence))[:12],
            window_7d=window_7d,
            window_30d=window_30d,
            recurrence=recurrence,
            intervention_comparison=intervention_comparison,
            calculation_trace=calculation_trace,
            insufficient_reasons=list(dict.fromkeys(insufficient_reasons))[:8],
        )
