import unittest

from app.agents.crisis_agent import CrisisAnalysis
from app.agents.evaluator_agent import EvaluatorAgent
from app.agents.safety_gate import SafetyDecision
from app.agents.rag_agent import RAGAnalysis
from app.rag.contracts import RetrievalCitation


class EvaluatorHandoffTests(unittest.TestCase):
    def setUp(self):
        self.evaluator = EvaluatorAgent()
        self.safety = SafetyDecision(decision="allow", redacted_message="test")

    def test_repaired_high_severity_text_issue_does_not_require_handoff(self):
        result = self.evaluator.evaluate(
            reply="",
            crisis=CrisisAnalysis(level="low"),
            safety=self.safety,
        )

        self.assertEqual(result.action, "revise")
        self.assertTrue(any(issue.severity == "high" for issue in result.issues))
        self.assertTrue(all(issue.fix_applied for issue in result.issues))
        self.assertFalse(result.requires_human_review)

    def test_clinical_high_risk_still_requires_handoff(self):
        result = self.evaluator.evaluate(
            reply="我在这里陪着你。",
            crisis=CrisisAnalysis(
                level="high",
                action="crisis_response",
                requires_human_review=True,
            ),
            safety=self.safety,
        )

        self.assertEqual(result.action, "escalate")
        self.assertTrue(result.requires_human_review)

    def test_unsupported_recommendation_is_removed_when_rag_is_present(self):
        citation = RetrievalCitation(
            source="睡眠指南", title="睡眠指南", document_id="sleep-doc", category="sleep_management",
            chunk_id="sleep-1", content="睡前减少高刺激内容并记录入睡时间。",
            score=0.9, file_path="guide.pdf", file_name="guide.pdf", file_type="pdf",
            content_hash="a" * 64, document_hash="b" * 64, char_start=0, char_end=20,
        )
        rag = RAGAnalysis(
            query="睡不着", rewritten_query="睡不着", selected_categories=["sleep_management"],
            top_k=1, min_score=0.2, has_evidence=True, citations=[citation], confidence=0.9,
        )
        result = self.evaluator.evaluate(
            reply="建议睡前减少高刺激内容并记录入睡时间。建议立刻服用安眠药。\n参考：睡眠指南 / sleep-1",
            crisis=CrisisAnalysis(level="low"), safety=self.safety, rag=rag,
        )
        self.assertIn("减少高刺激内容", result.final_reply)
        self.assertNotIn("服用安眠药", result.final_reply)
        self.assertNotIn("参考", result.final_reply)
        self.assertNotIn("睡眠指南", result.final_reply)
        self.assertTrue(any(issue.code == "unsupported_recommendation" for issue in result.issues))

    def test_rag_validation_never_returns_citation_only_reply(self):
        citation = RetrievalCitation(
            source="学生睡眠管理与失眠求助指南",
            title="学生睡眠管理与失眠求助指南",
            document_id="sleep-doc",
            category="sleep_management",
            chunk_id="sleep-1",
            content="固定起床时间，睡前减少手机等高刺激内容，并记录入睡和白天状态。",
            score=0.9,
            file_path="sleep.pdf",
            file_name="sleep.pdf",
            file_type="pdf",
            content_hash="a" * 64,
            document_hash="b" * 64,
            char_start=0,
            char_end=36,
        )
        rag = RAGAnalysis(
            query="很晚才能睡着怎么办",
            rewritten_query="低负担睡眠改善方法",
            selected_categories=["sleep_management"],
            top_k=1,
            min_score=0.2,
            has_evidence=True,
            citations=[citation],
            confidence=0.9,
        )

        result = self.evaluator.evaluate(
            reply="建议立刻服用安眠药。\n\n参考资料：[1]《学生睡眠管理与失眠求助指南》",
            crisis=CrisisAnalysis(level="low"),
            safety=self.safety,
            rag=rag,
        )

        self.assertIn("固定起床时间", result.final_reply)
        self.assertIn("睡前减少", result.final_reply)
        self.assertNotIn("服用安眠药", result.final_reply)
        self.assertNotIn("参考资料", result.final_reply)
        self.assertNotIn("学生睡眠管理与失眠求助指南", result.final_reply)
        self.assertTrue(any(
            issue.code == "empty_reply" and issue.fix_applied
            for issue in result.issues
        ))

        empty_result = self.evaluator.evaluate(
            reply="",
            crisis=CrisisAnalysis(level="low"),
            safety=self.safety,
            rag=rag,
        )
        self.assertIn("固定起床时间", empty_result.final_reply)
        self.assertNotIn("现在最困扰你的是什么", empty_result.final_reply)

    def test_internal_rag_ids_and_titles_are_removed_from_user_reply(self):
        citations = [
            RetrievalCitation(
                source="高校心理支持与校内求助指南",
                title="高校心理支持与校内求助指南",
                document_id=f"school-doc-{index}",
                category="school_resources",
                chunk_id=f"school_resources-2994827c1021000{index}-94be0442",
                content="学校心理中心预约可从官网、公众号、预约系统或现场服务台查询。",
                score=0.9,
                file_path=f"guide-{index}.pdf",
                file_name=f"guide-{index}.pdf",
                file_type="pdf",
                content_hash=(str(index) * 64),
                document_hash=(str(index + 2) * 64),
                char_start=0,
                char_end=30,
            )
            for index in (1, 2)
        ]
        rag = RAGAnalysis(
            query="怎么预约学校心理中心",
            rewritten_query="学校心理中心预约入口",
            selected_categories=["school_resources"],
            top_k=2,
            min_score=0.2,
            has_evidence=True,
            citations=citations,
            confidence=0.9,
        )
        raw = (
            "根据校内求助指南，学校心理中心的预约可以从官网、公众号、预约系统或现场服务台查询。"
            "高校心理支持与校内求助指南/school_resources-2994827c10210001-94be0442"
            "高校心理支持与校内求助指南/school_resources-2994827c10210002-94be0442"
        )

        result = self.evaluator.evaluate(
            reply=raw,
            crisis=CrisisAnalysis(level="low"),
            safety=self.safety,
            rag=rag,
        )

        self.assertNotIn("school_resources-", result.final_reply)
        self.assertIn("官网、公众号、预约系统", result.final_reply)
        self.assertNotIn("高校心理支持与校内求助指南", result.final_reply)
        self.assertNotIn("参考资料", result.final_reply)
        self.assertEqual(result.validated_rag_chunk_ids, [item.chunk_id for item in citations])


if __name__ == "__main__":
    unittest.main()
