import json
import tempfile
import unittest
from pathlib import Path

from modules.delivery_logger import build_delivery_log
from modules.news_memory import check_duplicate_news, load_news_memory, write_dedup_log


class FakeLLM:
    def __init__(self, duplicate: bool, reason: str = "semantic decision") -> None:
        self.duplicate = duplicate
        self.reason = reason

    def judge_news_duplicate(self, historical_news, current_news):
        return {"duplicate": self.duplicate, "reason": self.reason}


def news_item(title: str, url: str, company: str = "Meta", topic: str = "AI广告工具"):
    return {
        "news": {"title": title, "url": url, "published": "2026-07-29", "description": "news summary"},
        "analysis": {"company": company, "ai_application_area": topic, "category": "AI Advertising"},
    }


class NewsMemoryTests(unittest.TestCase):
    def setUp(self):
        self.memory = [{
            "title": "Meta launches AI advertising tools", "company": "Meta", "topic": "AI广告工具",
            "category": "AI Advertising", "published_date": "2026-07-28", "url": "https://example.com/meta-launch",
            "summary": "launch", "created_at": "2026-07-29T09:00:00",
        }]

    def test_same_url_is_duplicate(self):
        decision = check_duplicate_news(news_item("Another title", "https://example.com/meta-launch"), self.memory, FakeLLM(False))
        self.assertTrue(decision["duplicate"])

    def test_same_company_and_topic_semantic_match_is_duplicate(self):
        decision = check_duplicate_news(news_item("Meta expands AI advertising capabilities", "https://example.com/meta-expand"), self.memory, FakeLLM(True))
        self.assertTrue(decision["duplicate"])

    def test_new_customer_adoption_is_kept(self):
        decision = check_duplicate_news(news_item("Meta AI advertising tools win first enterprise customer", "https://example.com/meta-customer"), self.memory, FakeLLM(False, "new customer adoption"))
        self.assertFalse(decision["duplicate"])

    def test_missing_memory_file_is_initialized(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "history" / "news_memory.json"
            self.assertEqual(load_news_memory(str(path)), [])
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), [])

    def test_invalid_memory_file_recovers_to_empty_list(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "news_memory.json"
            path.write_text("not valid json", encoding="utf-8")
            self.assertEqual(load_news_memory(str(path)), [])
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), [])

    def test_duplicate_news_is_written_to_dedup_log(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "logs" / "dedup_log.json"
            decision = check_duplicate_news(news_item("Repeat", "https://example.com/meta-launch"), self.memory, FakeLLM(False))
            write_dedup_log([{"item": news_item("Repeat", "https://example.com/meta-launch"), "decision": decision}], str(path))
            records = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(len(records), 1)
            self.assertTrue(records[0]["duplicate"])
            self.assertEqual(records[0]["matched_news"], "Meta launches AI advertising tools")

    def test_non_duplicate_is_not_written_to_dedup_log(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dedup_log.json"
            decision = check_duplicate_news(news_item("New customer", "https://example.com/new"), self.memory, FakeLLM(False))
            write_dedup_log([{"item": news_item("New customer", "https://example.com/new"), "decision": decision}], str(path))
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), [])

    def test_missing_dedup_log_is_initialized(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "logs" / "dedup_log.json"
            write_dedup_log([], str(path))
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), [])

    def test_delivery_log_contains_dedup_metrics(self):
        record = build_delivery_log(run_date="2026-07-29")
        for key in ("fetched_items", "analyzed_items", "duplicates_removed", "final_selected", "memory_size"):
            self.assertIn(key, record)


if __name__ == "__main__":
    unittest.main()
