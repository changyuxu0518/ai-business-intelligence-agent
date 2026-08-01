from __future__ import annotations

from typing import Any


def rank_news(
    analysis_results: list[dict[str, Any]],
    preferences: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    return sorted(
        analysis_results,
        key=lambda item: score_news(item, preferences),
        reverse=True,
    )


def score_news(
    item: dict[str, Any], preferences: dict[str, Any] | None = None
) -> int:
    """Return the same final score used for ranking and audit logs."""
    return _final_score(item, preferences or {})


def summarize_ranked_news(ranked_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries = []
    for item in ranked_results:
        news = item.get("news", {})
        analysis = item.get("analysis", {})
        summaries.append(
            {
                "title": str(news.get("title", "")),
                "category": str(analysis.get("category", "Other") or "Other"),
                "importance_score": _importance_score(item),
                "business_impact": str(analysis.get("business_impact", "")),
                "takeaway": str(analysis.get("takeaway", "")),
            }
        )
    return summaries


def _final_score(item: dict[str, Any], preferences: dict[str, Any]) -> int:
    score = _importance_score(item) + _application_priority(item)
    analysis = item.get("analysis", {})
    news = item.get("news", {})
    category = str(analysis.get("category", "Other") or "Other")
    candidate_category = str(news.get("candidate_category", "business_trend"))
    score += {"enterprise_application": 3, "ai_industry": 1, "business_trend": 0}.get(candidate_category, 0)
    searchable_text = " ".join(
        [
            str(news.get("title", "")),
            str(news.get("description", "")),
            str(analysis.get("summary", "")),
            str(analysis.get("business_impact", "")),
            str(analysis.get("takeaway", "")),
        ]
    ).lower()

    if category in preferences.get("preferred_categories", []):
        score += 1
    if category in preferences.get("reduced_categories", []):
        score -= 1

    for topic in preferences.get("preferred_topics", []):
        if str(topic).lower() in searchable_text:
            score += 1
            break

    for topic in preferences.get("blocked_topics", []):
        if str(topic).lower() in searchable_text:
            score -= 1
            break

    return max(1, min(score, 6))


def _application_priority(item: dict[str, Any]) -> int:
    """Favor concrete enterprise AI adoption while retaining the LLM importance score."""
    analysis = item.get("analysis", {})
    news = item.get("news", {})
    score = 0

    if analysis.get("company") and analysis.get("ai_application_area"):
        score += 1
    if analysis.get("business_problem") and analysis.get("after_ai"):
        score += 1
    if analysis.get("business_model_impact") or analysis.get("product_opportunity"):
        score += 1
    if str(analysis.get("company", "")).strip().lower() in {"", "unknown", "未明确"}:
        score -= 2

    technical_text = " ".join(
        [str(news.get("title", "")), str(news.get("description", ""))]
    ).lower()
    technical_terms = ("benchmark", "gpu", "chip", "model release", "funding", "融资", "芯片", "基准测试")
    if any(term in technical_text for term in technical_terms):
        score -= 2
    return score


def _importance_score(item: dict[str, Any]) -> int:
    analysis = item.get("analysis", {})
    try:
        score = int(analysis.get("importance_score", 1))
    except (TypeError, ValueError):
        score = 1
    return max(1, min(score, 5))
