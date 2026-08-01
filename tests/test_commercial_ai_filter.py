import json
import tempfile
import unittest
from pathlib import Path

from modules.commercial_ai_filter import (
    filter_commercial_ai_news,
    is_commercial_ai_qualified,
    write_commercial_ai_discard_log,
)


def commercial_case(**overrides):
    analysis = {
        "company": "Klarna",
        "business_scenario": "AI客户服务",
        "business_model_impact": "客服产能从增加人工坐席转为软件自动处理与人工协同。",
        "importance_score": 5,
    }
    analysis.update(overrides)
    return {
        "news": {
            "title": "Klarna deploys AI customer service",
            "candidate_category": "enterprise_application",
        },
        "analysis": analysis,
    }


class CommercialAIQualificationTests(unittest.TestCase):
    def test_named_company_application_and_business_impact_qualify(self):
        self.assertTrue(is_commercial_ai_qualified(commercial_case()))

    def test_unknown_or_placeholder_fields_are_discarded(self):
        cases = (
            (commercial_case(company="unknown"), "missing_or_unknown_company"),
            (
                commercial_case(business_scenario="Other", ai_application_area="Other"),
                "missing_or_generic_ai_application",
            ),
            (
                commercial_case(business_model_impact="现有信息无法确认。"),
                "missing_or_unknown_business_impact",
            ),
        )
        for item, expected_reason in cases:
            with self.subTest(reason=expected_reason):
                qualified, discarded = filter_commercial_ai_news([item])
                self.assertEqual(qualified, [])
                self.assertIn(expected_reason, discarded[0]["discard_reason"])
                self.assertIsInstance(discarded[0]["score"], int)

    def test_concrete_fallback_is_used_when_primary_field_is_other(self):
        item = commercial_case(
            business_scenario="Other", ai_application_area="AI客服工单自动分流"
        )
        self.assertTrue(is_commercial_ai_qualified(item))

    def test_discard_log_has_required_fields(self):
        _, discarded = filter_commercial_ai_news(
            [commercial_case(company="unknown")]
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "commercial_ai_discard_log.json"
            write_commercial_ai_discard_log(discarded, str(path))
            records = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(
            set(records[0]), {"title", "discard_reason", "score"}
        )


if __name__ == "__main__":
    unittest.main()
