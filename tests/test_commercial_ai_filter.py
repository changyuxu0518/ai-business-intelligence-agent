import json
import tempfile
import unittest
from pathlib import Path

from modules.commercial_ai_filter import (
    classify_commercial_ai_item,
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
        item = commercial_case()
        self.assertTrue(is_commercial_ai_qualified(item))
        classify_commercial_ai_item(item)
        self.assertEqual(item["commercial_ai_status"], "confirmed")
        self.assertEqual(item["evidence_score"], 1.0)
        self.assertIsInstance(item["commercial_ai_reason"], list)

    def test_missing_partial_evidence_is_potential(self):
        cases = (
            (commercial_case(company="unknown"), "missing_or_unknown_company", 0.75),
            (
                commercial_case(business_model_impact="现有信息无法确认。"),
                "missing_or_unknown_business_impact",
                0.65,
            ),
        )
        for item, expected_reason, expected_score in cases:
            with self.subTest(reason=expected_reason):
                confirmed, potential, discarded = filter_commercial_ai_news([item])
                self.assertEqual(confirmed, [])
                self.assertEqual(potential, [item])
                self.assertEqual(discarded, [])
                self.assertIn(expected_reason, item["commercial_ai_reason"])
                self.assertEqual(item["evidence_score"], expected_score)

    def test_missing_concrete_application_is_discarded(self):
        item = commercial_case(
            business_scenario="Other", ai_application_area="Other"
        )
        confirmed, potential, discarded = filter_commercial_ai_news([item])
        self.assertEqual(confirmed, [])
        self.assertEqual(potential, [])
        self.assertIn(
            "missing_or_generic_ai_application",
            discarded[0]["commercial_ai_reason"],
        )
        self.assertIsInstance(discarded[0]["score"], int)

    def test_concrete_fallback_is_used_when_primary_field_is_other(self):
        item = commercial_case(
            business_scenario="Other", ai_application_area="AI客服工单自动分流"
        )
        self.assertTrue(is_commercial_ai_qualified(item))

    def test_partial_evidence_is_potential(self):
        item = commercial_case(business_model_impact="")
        confirmed, potential, discarded = filter_commercial_ai_news([item])
        self.assertEqual(confirmed, [])
        self.assertEqual(potential, [item])
        self.assertEqual(discarded, [])
        self.assertEqual(item["commercial_ai_status"], "potential")
        self.assertEqual(item["evidence_score"], 0.65)

    def test_discard_log_has_required_fields(self):
        _, _, discarded = filter_commercial_ai_news(
            [commercial_case(business_scenario="Other", ai_application_area="Other")]
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "commercial_ai_discard_log.json"
            write_commercial_ai_discard_log(discarded, str(path))
            records = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(
            set(records[0]),
            {
                "title",
                "commercial_ai_status",
                "commercial_ai_reason",
                "evidence_score",
                "score",
            },
        )


if __name__ == "__main__":
    unittest.main()
