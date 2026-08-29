import unittest

from app.agents.assessment_report_agent import AssessmentReportAgent
from app.schemas import ModelChatResponse


class FixedGateway:
    async def chat(self, request):
        return ModelChatResponse(
            content=(
                '{"emotionalAnalysis":"情绪有波动。",'
                '"physicalSymptoms":"建议观察睡眠。",'
                '"cognitiveStatus":"注意力可能受影响。",'
                '"suggestions":"保持作息并寻求支持。",'
                '"summary":"这是筛查结果。"}'
            ),
            model="test-model",
        )


class AssessmentReportAgentTests(unittest.IsolatedAsyncioTestCase):
    async def test_generates_complete_structured_report(self):
        report, response = await AssessmentReportAgent(FixedGateway()).generate(
            score=45,
            level="轻度抑郁",
            answers=[1] * 20,
        )

        self.assertEqual(response.model, "test-model")
        self.assertEqual(set(report), {
            "emotionalAnalysis", "physicalSymptoms", "cognitiveStatus", "suggestions", "summary"
        })
        self.assertTrue(all(report.values()))
