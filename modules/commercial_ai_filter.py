"""Final qualification gate for reportable commercial AI application cases."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from modules.news_ranker import score_news


UNKNOWN_EXACT_VALUES = {
    "",
    "unknown",
    "other",
    "n/a",
    "na",
    "none",
    "null",
    "未知",
    "未明确",
    "不明确",
    "其他",
    "无法确认",
    "现有信息无法确认",
}
UNKNOWN_PHRASES = (
    "无法确认",
    "不能确认",
    "尚不清楚",
    "尚未明确",
    "信息不足",
    "待确认",
    "not confirmed",
    "cannot confirm",
    "unclear",
)
GENERIC_AI_APPLICATIONS = {
    "ai",
    "ai application",
    "ai applications",
    "artificial intelligence",
    "人工智能",
    "ai应用",
    "ai应用场景",
    "大模型",
    "生成式ai",
    "生成式人工智能",
}


def commercial_ai_discard_reasons(item: dict[str, Any]) -> list[str]:
    """Explain why an analyzed item is not safe to publish as a commercial AI case."""
    analysis = item.get("analysis", {})
    company = commercial_ai_company(item)
    application = commercial_ai_application(item)
    impact = commercial_ai_business_impact(item)

    reasons = []
    if not _is_meaningful(company):
        reasons.append("missing_or_unknown_company")
    if not _is_concrete_ai_application(application):
        reasons.append("missing_or_generic_ai_application")
    # The report renderer explicitly requires a known business impact. A workflow
    # change alone is useful evidence, but must not create a formal report item
    # whose business-impact section is unknown.
    if not _is_meaningful(impact):
        reasons.append("missing_or_unknown_business_impact")
    return reasons


def is_commercial_ai_qualified(item: dict[str, Any]) -> bool:
    """Return true only for a named, concrete, commercially meaningful AI case."""
    return not commercial_ai_discard_reasons(item)


def commercial_ai_company(item: dict[str, Any]) -> str:
    analysis = item.get("analysis", {})
    return str(
        _first_meaningful(analysis.get("entity"), analysis.get("company")) or ""
    ).strip()


def commercial_ai_application(item: dict[str, Any]) -> str:
    analysis = item.get("analysis", {})
    return str(
        _first_concrete_application(
            analysis.get("business_scenario"), analysis.get("ai_application_area")
        )
        or ""
    ).strip()


def commercial_ai_business_impact(item: dict[str, Any]) -> str:
    analysis = item.get("analysis", {})
    return str(
        _first_meaningful(
            analysis.get("business_model_impact"), analysis.get("business_impact")
        )
        or ""
    ).strip()


def filter_commercial_ai_news(
    ranked_results: list[dict[str, Any]],
    preferences: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Keep qualified cases in rank order and return structured discard records."""
    qualified = []
    discarded = []
    for item in ranked_results:
        reasons = commercial_ai_discard_reasons(item)
        if not reasons:
            qualified.append(item)
            continue
        news = item.get("news", {})
        analysis = item.get("analysis", {})
        discarded.append(
            {
                "title": str(news.get("title") or analysis.get("title") or ""),
                "discard_reason": "; ".join(reasons),
                "score": score_news(item, preferences),
            }
        )
    return qualified, discarded


def write_commercial_ai_discard_log(
    discarded: list[dict[str, Any]],
    output_path: str = "outputs/logs/commercial_ai_discard_log.json",
) -> str:
    """Write the current run's qualification rejects, including an empty run."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(discarded, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return str(path)


def _is_meaningful(value: Any) -> bool:
    text = str(value or "").strip()
    normalized = text.casefold().rstrip("。.!！")
    if len(normalized) < 2 or normalized in UNKNOWN_EXACT_VALUES:
        return False
    return not any(phrase in normalized for phrase in UNKNOWN_PHRASES)


def _is_concrete_ai_application(value: Any) -> bool:
    text = str(value or "").strip().casefold().rstrip("。.!！")
    return _is_meaningful(text) and text not in GENERIC_AI_APPLICATIONS


def _first_meaningful(*values: Any) -> Any:
    return next((value for value in values if _is_meaningful(value)), "")


def _first_concrete_application(*values: Any) -> Any:
    return next((value for value in values if _is_concrete_ai_application(value)), "")
