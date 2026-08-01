import unittest

from modules.report_generator import generate_daily_report


class ReportGeneratorTests(unittest.TestCase):
    def test_item_without_process_or_impact_is_not_rendered(self):
        item = {
            "news": {
                "title": "Generic AI story",
                "candidate_category": "ai_industry",
            },
            "analysis": {
                "company": "Example",
                "before_ai": "",
                "after_ai": "",
                "business_model_impact": "现有信息无法确认。",
            },
        }
        report = generate_daily_report([item], "摘要不应让无效条目进入正文")
        self.assertNotIn("Generic AI story", report)
        self.assertNotIn("现有信息无法确认", report)

    def test_complete_process_and_impact_is_rendered(self):
        item = {
            "news": {
                "title": "Klarna deploys AI support",
                "source": "Example",
                "candidate_category": "enterprise_application",
            },
            "analysis": {
                "company": "Klarna",
                "category": "AI Enterprise",
                "business_scenario": "AI客户服务",
                "before_ai": "人工逐一处理所有咨询。",
                "after_ai": "AI先处理常规咨询，人工接管复杂问题。",
                "business_model_impact": "客服扩容从增加坐席转为增加自动化处理能力。",
            },
        }
        report = generate_daily_report([item], "有效摘要")
        self.assertIn("Klarna deploys AI support", report)
        self.assertIn("客服扩容从增加坐席", report)

    def test_unknown_company_is_not_rendered(self):
        item = {
            "news": {
                "title": "Unknown company deploys AI",
                "candidate_category": "enterprise_application",
            },
            "analysis": {
                "company": "unknown",
                "business_scenario": "AI客户服务",
                "business_model_impact": "自动化改变了客服处理能力的扩展方式。",
            },
        }
        report = generate_daily_report([item], "无效摘要")
        self.assertNotIn("Unknown company deploys AI", report)
        self.assertNotIn("企业/品牌：unknown", report)


if __name__ == "__main__":
    unittest.main()
