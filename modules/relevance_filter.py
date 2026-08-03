"""Fast, explainable relevance and output-quality gates for AI business news."""

from __future__ import annotations

import re
from typing import Any


AI_TERMS = (
    "artificial intelligence", "generative ai", "agentic", "ai agent", "machine learning",
    "large language model", "llm", "人工智能", "生成式ai", "生成式人工智能", "大模型",
    "智能体", "ai ", " ai", "openai", "anthropic", "gemini", "copilot",
)
BUSINESS_USE_TERMS = (
    "customer service", "客服", "客户服务", "workflow", "工作流", "automation", "自动化",
    "sales", "营销", "marketing", "advertising", "广告", "employee", "员工", "运营",
    "recruit", "招聘", "claims", "理赔", "healthcare", "医疗", "productivity", "生产力",
    "deploy", "deployment", "adopt", "adoption", "uses ai", "using ai", "integrat",
    "推出ai", "使用ai", "部署ai", "接入ai", "引入ai", "ai客户", "ai客服",
)
INDUSTRY_EXCEPTION_TERMS = (
    "model launch", "model release", "foundation model", "模型发布", "发布模型", "新模型",
    "ai regulation", "ai act", "人工智能监管", "ai监管", "监管", "policy", "政策",
    "ecosystem", "生态", "platform change", "平台变更", "developer ecosystem", "开发者生态",
)
FINANCE_NOISE_TERMS = (
    "成交额", "沪深", "股市", "股票", "a股", "指数", "涨停", "上涨", "下跌",
    "price target", "shares rise", "stock rises", "market cap", "财报", "earnings",
    "芯片价格", "chip price",
)
LOW_VALUE_TERMS = (
    "stock price", "share price", "shares rise", "shares fall", "price target",
    "market cap", "股价", "股票", "涨停", "跌停", "市值",
    "raises $", "raised $", "nabs $", "secures $", "raises funding", "funding round", "series a", "series b",
    "series c", "seed round", "融资", "募资", "筹资",
    "appoints ceo", "names ceo", "chief executive", "executive departure",
    "高管变动", "任命ceo", "任命首席执行官", "离任",
    "lock-up period", "lockup period", "禁售期",
    "registers company", "incorporates", "company registration", "注册公司",
    "ai investment", "invests in ai", "ai spending", "ai bet", "投资人工智能",
    "投资ai", "ai投资",
)
UNKNOWN_VALUES = {
    "", "unknown", "未明确", "n/a", "none", "other", "现有信息无法确认。",
    "现有信息无法确认", "无法确认", "不明确",
}


def evaluate_ai_relevance(title: str, content: str = "", source: str = "") -> dict[str, Any]:
    """Return a stable 1-5 relevance decision without spending an LLM request."""
    text = " ".join((title or "", content or "", source or "")).lower()
    has_ai = any(term in text for term in AI_TERMS)
    has_business_use = any(term in text for term in BUSINESS_USE_TERMS)
    is_industry_exception = has_ai and any(term in text for term in INDUSTRY_EXCEPTION_TERMS)
    is_finance_noise = any(term in text for term in FINANCE_NOISE_TERMS)

    if is_finance_noise and not has_business_use:
        return {"relevant": False, "score": 1, "reason": "通用财经或市场价格新闻，未见明确的AI商业应用。"}
    if has_ai and has_business_use:
        return {"relevant": True, "score": 5, "reason": "包含AI能力与明确业务场景，属于企业AI应用信号。"}
    if is_industry_exception:
        return {"relevant": True, "score": 3, "reason": "属于模型、监管或生态层面的重要AI行业动态，保留为AI行业情报。"}
    if has_ai:
        return {"relevant": True, "score": 3, "reason": "AI相关，但业务价值或落地场景暂不明确。"}
    return {"relevant": False, "score": 1, "reason": "未识别到AI商业应用或重要AI行业动态。"}


def filter_relevant_news(news_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep score >= 3 items and attach the decision for observability."""
    relevant_items = []
    for item in news_items:
        decision = evaluate_ai_relevance(
            str(item.get("title", "")), str(item.get("summary", item.get("content", ""))), str(item.get("source", ""))
        )
        item["relevance"] = decision
        if decision["relevant"] and decision["score"] >= 3:
            if any(term in (str(item.get("title", "")) + " " + str(item.get("summary", ""))).lower() for term in INDUSTRY_EXCEPTION_TERMS):
                item["candidate_category"] = "ai_industry"
            relevant_items.append(item)
    return relevant_items


def is_low_quality_analysis(item: dict[str, Any]) -> bool:
    """Apply the hard business-intelligence quality gate."""
    news = item.get("news", {})
    analysis = item.get("analysis", {})
    candidate_category = str(news.get("candidate_category", "business_trend"))

    if is_low_value_news(item) and not has_demonstrated_business_impact(item):
        return True
    if candidate_category == "enterprise_application":
        return not (
            is_qualified_enterprise_application(item)
            and has_reportable_business_analysis(item)
        )
    if candidate_category == "business_trend":
        return True
    return not has_reportable_business_analysis(item)


def filter_low_quality_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [item for item in results if not is_low_quality_analysis(item)]


def is_qualified_enterprise_application(item: dict[str, Any]) -> bool:
    """Require a company, an explicit AI adoption action, and a business scenario."""
    analysis = item.get("analysis", {})
    return bool(
        _meaningful(analysis.get("company"))
        and _meaningful(analysis.get("ai_adoption_action"))
        and _meaningful(
            analysis.get("business_scenario") or analysis.get("ai_application_area")
        )
    )


def has_reportable_business_analysis(item: dict[str, Any]) -> bool:
    """Return true only when workflow change and commercial impact are both clear."""
    analysis = item.get("analysis", {})
    before_ai = str(analysis.get("before_ai", "") or "").strip()
    after_ai = str(analysis.get("after_ai", "") or "").strip()
    impact = str(
        analysis.get("business_model_impact", "")
        or analysis.get("business_impact", "")
        or ""
    ).strip()
    return bool(
        _meaningful(before_ai)
        and _meaningful(after_ai)
        and before_ai.casefold() != after_ai.casefold()
        and _meaningful(impact)
    )


def has_demonstrated_business_impact(item: dict[str, Any]) -> bool:
    """Allow a low-value event only when it contains a real application case."""
    return is_qualified_enterprise_application(item) and has_reportable_business_analysis(item)


def is_low_value_news(item: dict[str, Any]) -> bool:
    news = item.get("news", item)
    analysis = item.get("analysis", {})
    text = " ".join(
        str(value or "")
        for value in (
            news.get("title"),
            news.get("description"),
            analysis.get("event_type"),
        )
    ).casefold()
    return any(term in text for term in LOW_VALUE_TERMS)


def select_daily_news(
    confirmed_results: list[dict[str, Any]],
    potential_results: list[dict[str, Any]],
    fallback_ranked_results: list[dict[str, Any]],
    max_items: int = 5,
    confirmed_limit: int = 3,
    potential_limit: int = 2,
    fallback_items: int = 3,
) -> list[dict[str, Any]]:
    """Select confirmed, then potential, with a business-relevant empty-result fallback."""
    limit = max(0, int(max_items))
    confirmed_count = min(limit, max(0, int(confirmed_limit)))
    selected = confirmed_results[:confirmed_count]

    remaining = limit - len(selected)
    potential_count = min(remaining, max(0, int(potential_limit)))
    selected.extend(potential_results[:potential_count])
    if selected:
        return selected

    fallback_limit = min(limit, max(0, int(fallback_items)))
    preferred_categories = {"business_trend", "enterprise_application"}
    preferred = [
        item
        for item in fallback_ranked_results
        if str(item.get("news", {}).get("candidate_category", ""))
        in preferred_categories
    ]
    remaining_ranked = [
        item
        for item in fallback_ranked_results
        if str(item.get("news", {}).get("candidate_category", ""))
        not in preferred_categories
    ]
    fallback = (preferred + remaining_ranked)[:fallback_limit]
    for item in fallback:
        item["selected_as_fallback"] = True
    return fallback


def _meaningful(value: Any) -> bool:
    text = str(value or "").strip()
    return text.casefold() not in UNKNOWN_VALUES and len(text) >= 2


def infer_company_from_text(title: str, content: str = "") -> str:
    """Conservative fallback for a named headline subject when the LLM omits it."""
    headline = (title or "").strip()
    patterns = (
        r"^([A-Z][A-Za-z0-9&.'-]*(?:\s+[A-Z][A-Za-z0-9&.'-]*){0,3})\s+(?:buys|acquires|deploys|launches|uses|adopts|integrates|partners|expands)\b",
        r"^([\u4e00-\u9fffA-Za-z0-9&.'-]{2,30})(?:宣布|推出|部署|收购|使用|接入).{0,12}(?:AI|人工智能|大模型|智能体)",
    )
    for pattern in patterns:
        match = re.search(pattern, headline, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return ""
