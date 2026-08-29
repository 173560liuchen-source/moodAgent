from __future__ import annotations

import json
from typing import Any

from ..model_gateway import ModelGateway, ModelGatewayError
from ..schemas import ChatMessage, ModelChatRequest, ModelChatResponse


class AssessmentReportAgent:
    """将 SDS 测评结果转换为结构化、非诊断性的心理支持报告。"""

    _fields = (
        "emotionalAnalysis",
        "physicalSymptoms",
        "cognitiveStatus",
        "suggestions",
        "summary",
    )

    def __init__(self, gateway: ModelGateway | None = None) -> None:
        self.gateway = gateway or ModelGateway()

    async def generate(
        self, *, score: int, level: str, answers: list[int] | None = None
    ) -> tuple[dict[str, str], ModelChatResponse]:
        prompt = self._prompt(score, level, answers or [])
        response = await self.gateway.chat(
            ModelChatRequest(
                messages=[
                    ChatMessage(
                        role="system",
                        content=(
                            "你是心理健康筛查报告助手。不得作出医学诊断或治疗承诺；"
                            "出现安全风险时只给出立即联系可信赖的人、当地紧急服务或专业机构的建议。"
                            "只输出合法 JSON。"
                        ),
                    ),
                    ChatMessage(role="user", content=prompt),
                ],
                temperature=0.2,
            )
        )
        return self._parse(response.content), response

    def _prompt(self, score: int, level: str, answers: list[int]) -> str:
        answer_text = "、".join(str(item) for item in answers[:20]) or "未提供"
        return f"""请根据以下 SDS 抑郁自评量表筛查结果生成结构化报告。

总分：{score}
标准分：{int(score * 1.25)}
筛查等级：{level}
各题作答（1-4）：{answer_text}

这是筛查结果，不是医学诊断。请用温和、明确的中文，避免夸大风险和作出诊断；建议必须可执行。严格只返回以下 JSON，五个字段均为字符串：
{{
  "emotionalAnalysis": "情绪状态分析",
  "physicalSymptoms": "躯体与睡眠相关线索分析",
  "cognitiveStatus": "认知与日常功能线索分析",
  "suggestions": "可执行建议；如存在紧急危险，建议立即求助",
  "summary": "总体筛查结论与下一步"
}}"""

    def _parse(self, content: str) -> dict[str, str]:
        text = content.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        payload: Any = json.loads(text.strip())
        if not isinstance(payload, dict):
            raise ModelGatewayError("测评报告模型未返回 JSON 对象")
        result = {field: str(payload.get(field, "")).strip() for field in self._fields}
        if any(not value for value in result.values()):
            raise ModelGatewayError("测评报告缺少必要字段")
        return result
