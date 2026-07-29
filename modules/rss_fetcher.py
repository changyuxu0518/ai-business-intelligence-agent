from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
import re
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

import feedparser
import yaml
from dateutil import parser as date_parser


# These terms prioritize reported business adoption before the limited LLM-analysis
# budget is consumed. They intentionally operate only on RSS title/summary text.
APPLICATION_SIGNALS = (
    "uses ai", "using ai", "used ai", "deploy", "adopt", "rollout", "launches ai",
    "customer service", "customer support", "shopping", "retail", "e-commerce",
    "advertis", "marketing", "brand", "sales", "workflow", "automation", "agent",
    "consumer", "enterprise", "operating cost", "product experience",
    "使用ai", "应用ai", "部署ai", "落地ai", "客户服务", "客服", "零售", "电商",
    "广告", "营销", "品牌", "销售", "工作流", "自动化", "智能体", "消费者", "运营成本",
)
TECHNICAL_SIGNALS = (
    "benchmark", "model release", "foundation model", "parameter", "gpu", "chip",
    "architecture", "training", "funding", "raises", "valuation", "融资", "模型发布",
    "基准测试", "参数", "芯片", "算力", "架构", "训练", "估值",
)
AI_SIGNALS = ("artificial intelligence", "人工智能", "大模型", "生成式")
MAX_CONTENT_LENGTH = 1800
AI_COMPANY_SIGNALS = ("openai", "anthropic", "deepmind", "hugging face", "nvidia", "meta ai")
ENTERPRISE_ADOPTER_SIGNALS = (
    "adopted ai", "deployed ai", "implemented ai", "using generative ai", "powered by ai",
    "ai transformation", "uses ai", "using ai", "使用ai", "部署ai", "落地ai",
)
CASE_SIGNALS = (
    "adopted ai", "deployed ai", "implemented ai", "using generative ai", "powered by ai",
    "ai transformation", "customer experience", "personalization", "advertising",
    "marketing automation", "sales automation", "workflow automation", "customer service",
    "采用ai", "部署ai", "实施ai", "客户体验", "个性化", "营销自动化", "销售自动化", "工作流自动化", "客服",
)


def fetch_recent_news(
    sources_file: str,
    lookback_days: int = 3,
    max_items_per_source: int = 20,
    timeout_seconds: int = 15,
) -> list[dict[str, str]]:
    """Fetch RSS items from configured sources and keep recent normalized items."""
    sources = _load_sources(sources_file)
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    items: list[dict[str, str]] = []

    for source in sources:
        parsed_feed = _fetch_feed(source["url"], timeout_seconds)
        if parsed_feed is None:
            print(f"Warning: failed to fetch RSS source: {source['name']}")
            continue
        if parsed_feed.bozo and not parsed_feed.entries:
            print(f"Warning: failed to parse RSS source: {source['name']}")
            continue

        for entry in parsed_feed.entries[:max_items_per_source]:
            normalized = _normalize_entry(entry, source)
            published_at = _parse_datetime(normalized["published_at"])
            if published_at is None or published_at < cutoff:
                continue
            items.append(normalized)

    return sorted(
        items,
        key=lambda item: (_candidate_priority(item), item["published_at"]),
        reverse=True,
    )


def _fetch_feed(url: str, timeout_seconds: int) -> Any | None:
    request = Request(url, headers={"User-Agent": "ai-business-daily-agent/0.1"})
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            content = response.read()
    except (TimeoutError, URLError, OSError):
        return None

    return feedparser.parse(content)


def _load_sources(sources_file: str) -> list[dict[str, str]]:
    with open(sources_file, "r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}

    sources = data.get("sources", [])
    if not isinstance(sources, list):
        raise ValueError("sources.yaml must contain a top-level 'sources' list.")

    valid_sources = []
    for source in sources:
        if not isinstance(source, dict):
            continue
        name = source.get("name")
        url = source.get("url")
        if not name or not url:
            continue
        valid_sources.append(
            {
                "name": str(name),
                "url": str(url),
                "region": str(source.get("region", "")),
                "category": str(source.get("category", "")),
                "source_category": str(source.get("source_category", "industry_trend")),
                "source_priority": _source_priority(source.get("source_priority")),
            }
        )

    if not valid_sources:
        raise ValueError("No valid RSS sources found.")

    return valid_sources


def _normalize_entry(entry: Any, source: dict[str, str]) -> dict[str, str]:
    published_at = (
        entry.get("published")
        or entry.get("updated")
        or entry.get("created")
        or ""
    )

    return {
        "title": _clean_text(entry.get("title", "")),
        "link": entry.get("link", ""),
        "source": source["name"],
        "published_at": _normalize_datetime_string(published_at),
        "summary": _clean_text(entry.get("summary", "")),
        "region": source.get("region", ""),
        "category": source.get("category", ""),
        "source_category": source.get("source_category", "industry_trend"),
        "source_priority": str(source.get("source_priority", 2)),
        "candidate_category": _candidate_category({
            "title": _clean_text(entry.get("title", "")),
            "summary": _clean_text(entry.get("summary", "")),
            "source_category": source.get("source_category", "industry_trend"),
        }),
    }


def _normalize_datetime_string(value: str) -> str:
    parsed = _parse_datetime(value)
    if parsed is None:
        return ""
    return parsed.astimezone(timezone.utc).isoformat()


def _parse_datetime(value: str) -> datetime | None:
    if not value:
        return None

    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError, OverflowError):
        try:
            parsed = date_parser.parse(value)
        except (TypeError, ValueError, OverflowError):
            return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _clean_text(value: str) -> str:
    content = str(value)
    content = re.sub(r"<(script|style|iframe|figure)[^>]*>.*?</\1>", " ", content, flags=re.IGNORECASE | re.DOTALL)
    content = re.sub(r"<img[^>]*>", " ", content, flags=re.IGNORECASE)
    content = re.sub(r"<[^>]+>", " ", content)
    return " ".join(unescape(content).split())[:MAX_CONTENT_LENGTH]


def _candidate_priority(item: dict[str, str]) -> int:
    """Prefer reported AI business adoption over AI-industry or technical updates."""
    text = f"{item.get('title', '')} {item.get('summary', '')}".lower()
    application_hits = sum(term.lower() in text for term in APPLICATION_SIGNALS)
    technical_hits = sum(term.lower() in text for term in TECHNICAL_SIGNALS)
    ai_mentioned = _has_ai_signal(text)
    # A general brand or marketing story is not an AI application case unless AI
    # is explicitly present in the reporting.
    if not ai_mentioned:
        return -4
    source_priority = _source_priority(item.get("source_priority"))
    source_bonus = (4 - source_priority) * 2
    case_score = _case_signal_score(text)
    role = _company_role(text)
    vendor_only = role == "ai_provider"
    vendor_penalty = 4 if vendor_only and application_hits < 2 else 0
    category_bonus = {"enterprise_application": 6, "ai_industry": 2, "business_trend": 1}[_candidate_category(item)]
    adopter_bonus = 3 if role == "enterprise_adopter" else 0
    return application_hits * 2 + case_score + source_bonus + category_bonus + adopter_bonus - technical_hits * 2 - vendor_penalty


def _has_ai_signal(text: str) -> bool:
    """Match AI as a word or Chinese compound, without treating 'campaign' as AI."""
    return (
        any(term.lower() in text for term in AI_SIGNALS)
        or bool(re.search(r"\bai\b|ai(?=[\u4e00-\u9fff])|(?<=[\u4e00-\u9fff])ai", text))
    )


def _is_ai_company_story(text: str) -> bool:
    return any(company in text for company in AI_COMPANY_SIGNALS)


def _case_signal_score(text: str) -> int:
    return sum(signal.lower() in text for signal in CASE_SIGNALS)


def _company_role(text: str) -> str:
    if any(company in text for company in AI_COMPANY_SIGNALS):
        return "ai_provider"
    if _has_ai_signal(text) and _case_signal_score(text) >= 2:
        return "enterprise_adopter"
    return "unknown"


def _source_priority(value: Any) -> int:
    try:
        return max(1, min(int(value), 3))
    except (TypeError, ValueError):
        return 2


def build_rss_quality_stats(items: list[dict[str, str]]) -> dict[str, Any]:
    """Summarize candidate quality and source contribution without changing item JSON."""
    category_counts = {
        "enterprise_application": 0,
        "ai_industry": 0,
        "business_trend": 0,
    }
    source_counts: dict[str, int] = {}
    role_counts = {"enterprise_adopter": 0, "ai_provider": 0, "unknown": 0}
    top_cases = []
    for item in items:
        quality = _rss_quality_category(item)
        category_counts[quality] += 1
        source = item.get("source", "Unknown")
        source_counts[source] = source_counts.get(source, 0) + 1
        role = _company_role(f"{item.get('title', '')} {item.get('summary', '')}".lower())
        role_counts[role] += 1
        if role == "enterprise_adopter" and _case_signal_score(f"{item.get('title', '')} {item.get('summary', '')}".lower()) > 0:
            top_cases.append({
                "company": _identified_company(f"{item.get('title', '')} {item.get('summary', '')}".lower()),
                "title": item.get("title", ""),
                "source": source,
                "company_role": role,
            })
    top_sources = [
        {"source": source, "articles": count}
        for source, count in sorted(source_counts.items(), key=lambda pair: (-pair[1], pair[0]))[:10]
    ]
    return {
        "candidate_analysis": category_counts,
        "case_discovery": role_counts,
        "top_enterprise_ai_cases": top_cases[:10],
        "top_sources": top_sources,
    }


def _rss_quality_category(item: dict[str, str]) -> str:
    return _candidate_category(item)


def _candidate_category(item: dict[str, str]) -> str:
    text = f"{item.get('title', '')} {item.get('summary', '')}".lower()
    application_hits = sum(term.lower() in text for term in APPLICATION_SIGNALS)
    technical_hits = sum(term.lower() in text for term in TECHNICAL_SIGNALS)
    if _has_ai_signal(text) and (_case_signal_score(text) >= 2 or application_hits >= 3) and _company_role(text) == "enterprise_adopter":
        return "enterprise_application"
    if technical_hits > application_hits:
        return "ai_industry"
    if item.get("source_category") == "ai_company" or _is_ai_company_story(text):
        return "ai_industry"
    return "business_trend"


def _identified_company(text: str) -> str:
    for company in ENTERPRISE_ADOPTER_SIGNALS:
        if company in text:
            return company
    return "未明确"
