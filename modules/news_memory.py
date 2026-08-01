"""Persistent, LLM-assisted deduplication for previously reported news."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path
import re
from typing import Any


_UNKNOWN_COMPANIES = {"", "unknown", "未明确", "n/a", "none"}
_UNKNOWN_EVENT_TYPES = {"", "other", "unknown", "未明确"}
_EVENT_PATTERNS = (
    ("funding", r"\b(?:raises?|raised|funding|seed round|series [a-z])\b|融资|募资|筹资"),
    ("stock_move", r"\b(?:stock|shares?|price target|market cap)\b|股价|股票|涨停|跌停|市值"),
    ("executive_change", r"\b(?:appoints?|names?|hires?|resigns?|chief executive|ceo)\b|高管|任命|离任"),
    ("company_registration", r"\b(?:registers?|incorporates?)\b|注册公司"),
    ("acquisition", r"\b(?:acquires?|acquired|acquisition|buys?|bought|merger)\b|收购|并购"),
    ("deployment", r"\b(?:deploys?|deployed|rolls? out|rolled out|implements?|implemented)\b|部署|上线|落地"),
    ("adoption", r"\b(?:adopts?|adopted|uses?|using|introduces?|introduced)\b|采用|使用|引入"),
    ("integration", r"\b(?:integrates?|integrated|integration|connects?|connected)\b|集成|接入|连接"),
    ("launch", r"\b(?:launches?|launched|releases?|released|unveils?|unveiled|expands?|expanded)\b|发布|推出|扩展"),
    ("regulation", r"\b(?:regulation|regulator|policy|law|act)\b|监管|法规|政策"),
    ("investment", r"\b(?:invests?|investment|ai spending)\b|投资"),
)
_KEYWORD_STOPWORDS = {
    "with", "from", "into", "that", "this", "will", "what", "why", "how",
    "company", "news", "report", "using", "uses", "launches", "launch",
    "the", "and", "for", "its", "new", "ai", "人工智能", "现有信息",
}


def load_news_memory(memory_path: str, memory_days: int = 90) -> list[dict[str, str]]:
    """Load retained memory, creating or recovering the file when necessary."""
    path = Path(memory_path)
    needs_rewrite = not path.exists()
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
        if not isinstance(data, list):
            raise ValueError("news memory must be a JSON list")
        memory = [item for item in data if isinstance(item, dict)]
    except (OSError, json.JSONDecodeError, ValueError):
        # A bad historical file must never prevent the daily report from running.
        memory = []
        needs_rewrite = True

    retained = _prune_expired_memory(memory, memory_days)
    # This also creates a missing file and replaces an unreadable JSON file safely.
    if needs_rewrite or retained != memory:
        save_news_memory(retained, memory_path, memory_days)
    return retained


def load_report_history(report_dir: str = "outputs/reports") -> list[dict[str, str]]:
    """Extract deduplication fingerprints from archived Markdown reports."""
    directory = Path(report_dir)
    if not directory.exists():
        return []

    entries: list[dict[str, str]] = []
    for path in sorted(directory.glob("*.md")):
        try:
            markdown = path.read_text(encoding="utf-8")
        except OSError:
            continue
        report_date = _report_date(markdown, path)
        entries.extend(_extract_report_entries(markdown, report_date))
    return entries


def save_news_memory(
    memory: list[dict[str, Any]], memory_path: str, memory_days: int = 90
) -> str:
    """Persist memory after applying the configured retention period."""
    path = Path(memory_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    retained = _prune_expired_memory(memory, memory_days)
    path.write_text(json.dumps(retained, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def add_news_to_memory(
    selected_news: list[dict[str, Any]],
    memory: list[dict[str, Any]],
    memory_path: str,
    memory_days: int = 90,
) -> list[dict[str, str]]:
    """Append only report-selected items and persist the resulting memory."""
    updated = list(memory)
    remembered_urls = {str(item.get("url", "")).strip() for item in updated}
    for item in selected_news:
        entry = _memory_entry(item)
        # A URL already retained does not need another identical memory record.
        if entry["url"] and entry["url"] in remembered_urls:
            continue
        updated.append(entry)
        if entry["url"]:
            remembered_urls.add(entry["url"])
    save_news_memory(updated, memory_path, memory_days)
    return _prune_expired_memory(updated, memory_days)


def check_duplicate_news(
    current_news: dict[str, Any],
    memory: list[dict[str, Any]],
    llm_client: Any,
) -> dict[str, Any]:
    """Return a duplicate decision for one analyzed news item.

    URL equality is deterministic.  For news from the same known company, the
    supplied LLM decides whether the two articles are the same business event
    and explicitly distinguishes a new lifecycle stage from a repeat report.
    LLM failures are fail-open so a transient API issue cannot hide news.
    """
    current = _memory_entry(current_news)
    current_url = current["url"]
    for historical in memory:
        if current_url and current_url == str(historical.get("url", "")).strip():
            return {
                "duplicate": True,
                "matched_news": str(historical.get("title", "")),
                "reason": "URL already exists in news memory.",
            }

    company = _normalized_company(current["company"])
    if not company:
        return {"duplicate": False, "matched_news": "", "reason": "No reliable company match for semantic comparison."}

    for historical in memory:
        if _normalized_company(str(historical.get("company", ""))) != company:
            continue
        similarity = _event_topic_similarity(current, historical)
        if similarity["highly_similar"]:
            return {
                "duplicate": True,
                "matched_news": str(historical.get("title", "")),
                "reason": (
                    "Same company with highly similar topic/event "
                    f"(topic={similarity['topic_score']:.2f}, "
                    f"event={similarity['event_match']})."
                ),
            }
        # Avoid an LLM comparison for clearly unrelated events from a prolific company.
        if similarity["topic_score"] < 0.15 and not similarity["event_match"]:
            continue
        try:
            decision = llm_client.judge_news_duplicate(historical, current)
        except Exception:
            continue
        if bool(decision.get("duplicate", False)):
            return {
                "duplicate": True,
                "matched_news": str(historical.get("title", "")),
                "reason": str(decision.get("reason", "Same business event as a historical report.")),
            }

    return {"duplicate": False, "matched_news": "", "reason": "No matching historical business event."}


def write_dedup_log(
    duplicate_results: list[dict[str, Any]],
    log_path: str = "outputs/logs/dedup_log.json",
    retention_days: int = 90,
) -> str:
    """Append this run's duplicate decisions and retain only recent log records.

    Each result may contain ``item`` and ``decision`` (the shape used by the
    pipeline), or already be a completed dedup-log record. Non-duplicates are
    deliberately ignored.
    """
    path = Path(log_path)
    try:
        existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
        if not isinstance(existing, list):
            raise ValueError("dedup log must be a JSON list")
    except (OSError, json.JSONDecodeError, ValueError):
        existing = []

    new_records = []
    for result in duplicate_results:
        decision = result.get("decision", result)
        if not bool(decision.get("duplicate", False)):
            continue
        item = result.get("item", result)
        entry = _memory_entry(item)
        new_records.append(
            {
                "title": entry["title"],
                "duplicate": True,
                "matched_news": str(decision.get("matched_news", "") or ""),
                "reason": str(decision.get("reason", "") or ""),
                "company": entry["company"],
                "event_type": entry["event_type"],
                "topic": entry["topic"],
                "topic_keywords": entry["topic_keywords"],
                "created_at": datetime.now().isoformat(timespec="seconds"),
            }
        )

    retained = _prune_expired_dedup_logs(existing + new_records, retention_days)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(retained, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def _memory_entry(item: dict[str, Any]) -> dict[str, str]:
    news = item.get("news", item)
    analysis = item.get("analysis", item)
    title = str(news.get("title", analysis.get("title", "")) or "")
    topic = str(
        analysis.get("business_scenario")
        or analysis.get("ai_application_area")
        or item.get("topic", "")
        or ""
    )
    event_type = str(
        analysis.get("event_type")
        or item.get("event_type")
        or _infer_event_type(f"{title} {news.get('description', '')}")
    )
    keywords_value = analysis.get("topic_keywords", item.get("topic_keywords", ""))
    topic_keywords = _keywords_text(keywords_value, f"{title} {topic}")
    return {
        "title": title,
        "company": str(analysis.get("company", item.get("company", "")) or ""),
        "event_type": event_type,
        "topic": topic,
        "topic_keywords": topic_keywords,
        "category": str(analysis.get("category", item.get("category", "Other")) or "Other"),
        "published_date": str(news.get("published", news.get("published_at", item.get("published_date", ""))) or ""),
        "url": str(news.get("url", news.get("link", analysis.get("url", item.get("url", "")))) or ""),
        "summary": str(
            analysis.get("summary")
            or news.get("description")
            or item.get("summary", "")
            or analysis.get("business_problem", "")
            or ""
        ),
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }


def _prune_expired_memory(memory: list[dict[str, Any]], memory_days: int) -> list[dict[str, str]]:
    cutoff = date.today() - timedelta(days=max(0, memory_days))
    retained = []
    for item in memory:
        created = _parse_date(str(item.get("created_at", "")))
        # Legacy entries without a usable date are retained rather than silently lost.
        if created is None or created >= cutoff:
            retained.append({key: str(item.get(key, "") or "") for key in _memory_keys()})
    return retained


def _parse_date(value: str) -> date | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _prune_expired_dedup_logs(records: list[dict[str, Any]], retention_days: int) -> list[dict[str, Any]]:
    cutoff = date.today() - timedelta(days=max(0, retention_days))
    return [
        record
        for record in records
        if _parse_date(str(record.get("created_at", ""))) is None
        or _parse_date(str(record.get("created_at", ""))) >= cutoff
    ]


def _normalized_company(value: str) -> str:
    normalized = value.strip().casefold()
    return "" if normalized in _UNKNOWN_COMPANIES else normalized


def _memory_keys() -> tuple[str, ...]:
    return (
        "title", "company", "event_type", "topic", "topic_keywords", "category",
        "published_date", "url", "summary", "created_at",
    )


def _extract_report_entries(markdown: str, report_date: str) -> list[dict[str, str]]:
    matches = list(
        re.finditer(r"(?m)^#{1,3}\s+(\d+)\.\s+(.+?)\s*$", markdown)
    )
    entries = []
    for index, match in enumerate(matches):
        block_end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        block = markdown[match.end():block_end]
        title = _clean_markdown(match.group(2))
        company = _field_from_block(block, ("企业/品牌", "Company"))
        if not company:
            company = _infer_company_from_title(title)
        topic = _field_from_block(
            block, ("AI应用场景", "AI application", "Category", "分类")
        )
        what_happened = _section_from_block(
            block, ("发生了什么", "What happened?", "What happened")
        )
        event_type = _infer_event_type(f"{title} {what_happened}")
        entries.append(
            {
                "title": title,
                "company": company,
                "event_type": event_type,
                "topic": topic,
                "topic_keywords": _keywords_text("", f"{title} {topic}"),
                "category": _field_from_block(block, ("分类", "Category")),
                "published_date": report_date,
                "url": _first_markdown_url(block),
                "summary": what_happened,
                "created_at": f"{report_date}T00:00:00" if report_date else "",
            }
        )
    return entries


def _event_topic_similarity(
    current: dict[str, str], historical: dict[str, Any]
) -> dict[str, Any]:
    current_event = str(current.get("event_type", "")).casefold()
    historical_event = str(historical.get("event_type", "")).casefold()
    event_match = bool(
        current_event
        and historical_event
        and current_event not in _UNKNOWN_EVENT_TYPES
        and historical_event not in _UNKNOWN_EVENT_TYPES
        and current_event == historical_event
    )
    current_keywords = _keyword_set(
        str(current.get("topic_keywords", "")),
        f"{current.get('title', '')} {current.get('topic', '')}",
    )
    historical_keywords = _keyword_set(
        str(historical.get("topic_keywords", "")),
        f"{historical.get('title', '')} {historical.get('topic', '')}",
    )
    # Company equality is already a prerequisite; do not let the company name
    # itself inflate topic similarity.
    company_tokens = set(re.findall(r"[a-z0-9][a-z0-9+.-]{1,}", current["company"].casefold()))
    current_keywords -= company_tokens
    historical_keywords -= company_tokens
    union = current_keywords | historical_keywords
    jaccard = len(current_keywords & historical_keywords) / len(union) if union else 0.0
    current_topic = _normalized_topic(f"{current.get('topic', '')} {' '.join(sorted(current_keywords))}")
    historical_topic = _normalized_topic(
        f"{historical.get('topic', '')} {' '.join(sorted(historical_keywords))}"
    )
    sequence = (
        SequenceMatcher(None, current_topic, historical_topic).ratio()
        if current_topic and historical_topic
        else 0.0
    )
    current_title = _normalized_topic(str(current.get("title", "")))
    historical_title = _normalized_topic(str(historical.get("title", "")))
    title_equal = bool(current_title and current_title == historical_title)
    topic_score = max(jaccard, sequence)
    both_events_unknown = (
        current_event in _UNKNOWN_EVENT_TYPES
        and historical_event in _UNKNOWN_EVENT_TYPES
    )
    return {
        "topic_score": topic_score,
        "event_match": event_match,
        "highly_similar": bool(
            (title_equal and (event_match or both_events_unknown))
            or (event_match and topic_score >= 0.35)
            or (both_events_unknown and topic_score >= 0.70)
        ),
    }


def _infer_event_type(text: str) -> str:
    normalized = _clean_markdown(text).casefold()
    for event_type, pattern in _EVENT_PATTERNS:
        if re.search(pattern, normalized, flags=re.IGNORECASE):
            return event_type
    return "other"


def _keywords_text(value: Any, fallback: str) -> str:
    if isinstance(value, list):
        supplied = [str(item).strip().casefold() for item in value if str(item).strip()]
    else:
        supplied = [
            part.strip().casefold()
            for part in re.split(r"[,，;；|]", str(value or ""))
            if part.strip()
        ]
    keywords = supplied or sorted(_keyword_set("", fallback))
    return ", ".join(dict.fromkeys(keywords[:12]))


def _keyword_set(value: str, fallback: str) -> set[str]:
    source = value or fallback
    english = re.findall(r"[a-z0-9][a-z0-9+.-]{1,}", source.casefold())
    chinese_chunks = re.findall(r"[\u4e00-\u9fff]{2,12}", source)
    tokens = english + chinese_chunks
    return {token for token in tokens if token not in _KEYWORD_STOPWORDS}


def _normalized_topic(value: str) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", value.casefold())


def _field_from_block(block: str, labels: tuple[str, ...]) -> str:
    for label in labels:
        match = re.search(
            rf"(?mi)^(?:[-*]\s*)?(?:\*\*)?{re.escape(label)}(?:\*\*)?\s*[：:]\s*(.+?)\s*$",
            block,
        )
        if match:
            return _clean_markdown(match.group(1))
    return ""


def _section_from_block(block: str, headings: tuple[str, ...]) -> str:
    for heading in headings:
        match = re.search(
            rf"(?ms)^#{{2,4}}\s+{re.escape(heading)}\s*$\s*(.*?)(?=^#{{1,4}}\s+|^---\s*$|\Z)",
            block,
        )
        if match:
            return _clean_markdown(match.group(1))
    return ""


def _first_markdown_url(block: str) -> str:
    match = re.search(r"\[[^\]]+\]\((https?://[^)]+)\)", block)
    return match.group(1).strip() if match else ""


def _clean_markdown(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", str(value or ""))
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"[*_`#]", "", text)
    return " ".join(text.split())


def _infer_company_from_title(title: str) -> str:
    match = re.match(
        r"^([A-Z][A-Za-z0-9&.'-]*(?:\s+[A-Z][A-Za-z0-9&.'-]*){0,2})"
        r"(?:['’]s|\s+(?:buys?|bought|acquires?|acquired|deploys?|deployed|"
        r"launches?|launched|uses?|adopts?|adopted|raises?|raised|agrees?))\b",
        title,
    )
    if match:
        return match.group(1).strip()
    possessive = re.search(r"\b([A-Z][A-Za-z0-9&.'-]{1,30})['’]s\b", title)
    return possessive.group(1).strip() if possessive else ""


def _report_date(markdown: str, path: Path) -> str:
    match = re.search(r"(?mi)^Date:\s*(\d{4}-\d{2}-\d{2})\s*$", markdown)
    if match:
        return match.group(1)
    filename_match = re.search(r"(\d{4}-\d{2}-\d{2})", path.name)
    return filename_match.group(1) if filename_match else ""
