from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote_plus

import feedparser

from modules.rss_fetcher import (
    _candidate_category,
    _case_signal_score,
    _company_role,
    _normalize_datetime_string,
)


DISCOVERY_QUERIES = (
    '"company uses generative AI"',
    '"enterprise deployed AI"',
    '"AI customer experience" case study',
    '"AI marketing" case study',
    '"AI workflow automation" enterprise',
    '"AI agent" business deployment',
)


def discover_enterprise_ai_cases(max_results: int = 10, lookback_days: int = 3) -> list[dict[str, str]]:
    """Find recent enterprise AI application reporting through bounded news RSS searches."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    results: list[dict[str, str]] = []
    seen_links: set[str] = set()
    for query in DISCOVERY_QUERIES:
        feed = feedparser.parse(f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=en-US&gl=US&ceid=US:en")
        for entry in feed.entries:
            link = str(entry.get("link", ""))
            published = _normalize_datetime_string(entry.get("published", entry.get("updated", "")))
            if not link or link in seen_links or not published:
                continue
            if datetime.fromisoformat(published) < cutoff:
                continue
            item = {
                "title": str(entry.get("title", "")),
                "link": link,
                "source": "Discovery Search",
                "published_at": published,
                "summary": str(entry.get("summary", "")),
                "region": "global",
                "category": "discovery",
                "source_category": "enterprise_case",
                "source_priority": "1",
                "source_type": "discovery",
            }
            item["candidate_category"] = _candidate_category(item)
            item["company_role"] = _company_role(f"{item['title']} {item['summary']}".lower())
            item["case_relevance_score"] = str(min(5, max(1, _case_signal_score(f"{item['title']} {item['summary']}".lower()))))
            results.append(item)
            seen_links.add(link)
    return sorted(results, key=lambda item: int(item["case_relevance_score"]), reverse=True)[:max_results]


def build_discovery_stats(items: list[dict[str, str]]) -> dict[str, int]:
    counts = {"retrieved": len(items), "enterprise_application": 0, "ai_industry": 0, "business_trend": 0}
    for item in items:
        category = item.get("candidate_category", "business_trend")
        counts[category] = counts.get(category, 0) + 1
    return counts
