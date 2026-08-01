import unittest

from modules.relevance_filter import (
    evaluate_ai_relevance,
    filter_low_quality_results,
    filter_relevant_news,
    has_reportable_business_analysis,
    infer_company_from_text,
    is_qualified_enterprise_application,
    select_daily_news,
)


class RelevanceFilterTests(unittest.TestCase):
    def test_generic_financial_news_is_rejected(self):
        decision = evaluate_ai_relevance("沪深两市成交额突破2万亿", "市场成交活跃")
        self.assertFalse(decision["relevant"])
        self.assertEqual(decision["score"], 1)

    def test_enterprise_ai_customer_service_is_kept(self):
        decision = evaluate_ai_relevance("Klarna AI customer service roadmap", "Klarna expands AI customer service")
        self.assertTrue(decision["relevant"])
        self.assertGreaterEqual(decision["score"], 3)

    def test_named_headline_subject_is_used_as_company_fallback(self):
        self.assertEqual(infer_company_from_text("Abridge buys agentic AI company"), "Abridge")

    def test_enterprise_application_requires_subject_action_and_scenario(self):
        complete = {
            "analysis": {
                "company": "Klarna",
                "ai_adoption_action": "部署AI客服",
                "business_scenario": "客户服务",
            }
        }
        self.assertTrue(is_qualified_enterprise_application(complete))
        for missing_field in ("company", "ai_adoption_action", "business_scenario"):
            incomplete = {"analysis": dict(complete["analysis"])}
            incomplete["analysis"][missing_field] = ""
            self.assertFalse(is_qualified_enterprise_application(incomplete))

    def test_reportable_analysis_requires_process_change_and_impact(self):
        complete = {
            "analysis": {
                "before_ai": "人工坐席逐一处理咨询",
                "after_ai": "AI先处理常规咨询，人工处理复杂问题",
                "business_model_impact": "服务成本由纯人工扩容转为软件与人工协同。",
            }
        }
        self.assertTrue(has_reportable_business_analysis(complete))
        complete["analysis"]["business_model_impact"] = "现有信息无法确认。"
        self.assertFalse(has_reportable_business_analysis(complete))

    def test_funding_without_application_evidence_is_removed(self):
        item = {
            "news": {
                "title": "Enigma raises $70M for AI robots",
                "description": "Seed round",
                "candidate_category": "ai_industry",
            },
            "analysis": {
                "company": "Enigma",
                "before_ai": "",
                "after_ai": "",
                "business_model_impact": "",
            },
        }
        self.assertEqual(filter_low_quality_results([item]), [])

    def test_daily_limit_does_not_backfill_or_apply_category_quotas(self):
        def item(category, rank):
            return {"news": {"candidate_category": category}, "rank": rank}

        ranked = [
            item("enterprise_application", 1),
            item("enterprise_application", 2),
            item("enterprise_application", 3),
            item("ai_industry", 4),
            item("ai_industry", 5),
            item("business_trend", 6),
        ]
        selected = select_daily_news(ranked, 5)
        self.assertEqual([entry["rank"] for entry in selected], [1, 2, 3, 4, 5])

        only_two_qualified = select_daily_news(ranked[:2], 5)
        self.assertEqual([entry["rank"] for entry in only_two_qualified], [1, 2])

    def test_model_launch_is_kept_as_industry_news(self):
        items = [{"title": "New foundation model launch", "summary": "AI model release", "source": "Example"}]
        kept = filter_relevant_news(items)
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0]["candidate_category"], "ai_industry")


if __name__ == "__main__":
    unittest.main()
