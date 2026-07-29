"""Persistent, LLM-assisted deduplication for previously reported news."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any


_UNKNOWN_COMPANIES = {"", "unknown", "未明确", "n/a", "none"}


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
                "topic": entry["topic"],
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
    return {
        "title": str(news.get("title", analysis.get("title", "")) or ""),
        "company": str(analysis.get("company", item.get("company", "")) or ""),
        "topic": str(analysis.get("ai_application_area", item.get("topic", "")) or ""),
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
    return ("title", "company", "topic", "category", "published_date", "url", "summary", "created_at")
