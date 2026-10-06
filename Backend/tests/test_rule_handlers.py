import unittest

from app.rules.rule_handlers import apply_selected_rules


class RuleHandlerTests(unittest.TestCase):
    def test_sales_rule_adds_sales_metadata(self):
        document = {"content": "sales update", "title": "Quarterly report"}

        result = apply_selected_rules(document, "Infor Sales Rules")

        self.assertEqual(result["rule_applied"], "Infor Sales Rules")
        self.assertIn("sales", result["tags"])
        self.assertEqual(result["metadata"]["category"], "sales")

    def test_support_rule_adds_priority(self):
        document = {"content": "support ticket", "title": "Issue"}

        result = apply_selected_rules(document, "L3 Ticket Rules")

        self.assertEqual(result["rule_applied"], "L3 Ticket Rules")
        self.assertEqual(result["metadata"]["priority"], "high")
        self.assertIn("support", result["tags"])

    def test_knowledge_rule_adds_summary(self):
        document = {"content": "knowledge base article", "title": "How to guide"}

        result = apply_selected_rules(document, "Knowledge Base Rules")

        self.assertEqual(result["rule_applied"], "Knowledge Base Rules")
        self.assertIn("knowledge", result["tags"])
        self.assertIn("summary", result["metadata"])


if __name__ == "__main__":
    unittest.main()
