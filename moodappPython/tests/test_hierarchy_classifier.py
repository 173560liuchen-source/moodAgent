import unittest

from app.rag.hierarchy_classifier import KnowledgeHierarchyClassifier


class KnowledgeHierarchyClassifierTest(unittest.TestCase):
    def setUp(self):
        self.classifier = KnowledgeHierarchyClassifier()

    def test_sleep_onset_problem(self):
        result = self.classifier.classify("我最近总是睡不着，怎么才能快点入睡？")
        self.assertEqual(result.matches[0].parent_category, "睡眠管理")
        self.assertIn("入睡困难", result.matches[0].child_categories)
        self.assertGreater(result.matches[0].confidence, 0.6)

    def test_multi_parent_question(self):
        result = self.classifier.classify("考试焦虑让我睡不着，学校心理中心怎么预约？")
        parents = {item.parent_category for item in result.matches}
        self.assertEqual(parents, {"压力管理", "睡眠管理", "情绪支持", "校园资源"})

    def test_crisis_is_classified_without_claiming_it_is_safe(self):
        result = self.classifier.classify("我现在不想活了，手边有药，该怎么办？")
        crisis = next(item for item in result.matches if item.parent_category == "危机干预")
        self.assertIn("自杀", crisis.child_categories)
        self.assertIn("紧急求助", crisis.child_categories)

    def test_unrelated_question_returns_no_match(self):
        result = self.classifier.classify("今天天气怎么样？")
        self.assertEqual(result.matches, [])


if __name__ == "__main__":
    unittest.main()
