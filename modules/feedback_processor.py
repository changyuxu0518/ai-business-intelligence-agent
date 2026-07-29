from __future__ import annotations

import json
from typing import Any

from modules.llm_client import LLMClient, LLMClientError


CATEGORIES = {
    "AI Advertising",
    "AI Marketing",
    "AI Product",
    "AI Consumer",
    "AI Enterprise",
    "AI Content Creation",
    "AI Regulation",
    "AI Industry Trend",
    "Other",
}


def process_feedback(feedback_text: str, llm_client: LLMClient | None = None) -> dict[str, Any]:
    if not feedback_text.strip():
        return _default_feedback("empty feedback")

    if llm_client is None:
        return _heuristic_feedback(feedback_text)

    prompt = _build_feedback_prompt(feedback_text)
    try:
        raw_response = llm_client._call_llm(prompt)
    except LLMClientError:
        return _heuristic_feedback(feedback_text)

    return parse_feedback_result(raw_response, fallback_text=feedback_text)


def parse_feedback_result(raw_response: str, fallback_text: str = "") -> dict[str, Any]:
    try:
        parsed = json.loads(_extract_json(raw_response))
    except (json.JSONDecodeError, ValueError):
        return _heuristic_feedback(fallback_text)

    if not isinstance(parsed, dict):
        return _heuristic_feedback(fallback_text)

    category = str(parsed.get("category", "Other") or "Other")
    if category not in CATEGORIES:
        category = "Other"

    preference_change = str(parsed.get("preference_change", parsed.get("action", "adjust")) or "adjust")
    if preference_change not in {"increase", "reduce", "block", "adjust"}:
        preference_change = "adjust"

    feedback_type = str(parsed.get("feedback_type", parsed.get("type", "adjustment")) or "adjustment")
    if feedback_type not in {"positive", "negative", "adjustment"}:
        feedback_type = "adjustment"

    return {
        "feedback_type": feedback_type,
        "category": category,
        "preference_change": preference_change,
        "reason": str(parsed.get("reason", "") or ""),
        "preferred_topics": _string_list(parsed.get("preferred_topics", [])),
        "blocked_topics": _string_list(parsed.get("blocked_topics", [])),
        "analysis_preference": str(parsed.get("analysis_preference", "") or ""),
        "raw_feedback": fallback_text,
    }


def _build_feedback_prompt(feedback_text: str) -> str:
    return f"""
You are an AI User Preference Analyst for an AI business news daily report product.

Convert the user's natural language feedback into structured preference data.

Classify:
- feedback_type: positive, negative, adjustment
- category: one of AI Advertising, AI Marketing, AI Product, AI Consumer, AI Enterprise, AI Content Creation, AI Regulation, AI Industry Trend, Other
- preference_change: increase, reduce, block, adjust
- preferred_topics: list of topics the user wants more
- blocked_topics: list of topics the user wants less or wants blocked
- analysis_preference: preferred analysis style if mentioned

Return JSON only. Do not use Markdown.

User feedback:
{feedback_text}

Return exactly this JSON schema:
{{
  "feedback_type": "",
  "category": "",
  "preference_change": "",
  "reason": "",
  "preferred_topics": [],
  "blocked_topics": [],
  "analysis_preference": ""
}}
""".strip()


def _heuristic_feedback(feedback_text: str) -> dict[str, Any]:
    text = feedback_text.lower()
    category = "Other"
    preferred_topics: list[str] = []
    blocked_topics: list[str] = []
    feedback_type = "adjustment"
    preference_change = "adjust"

    wants_less = any(token in text for token in ["减少", "少", "不要", "不喜欢", "less", "reduce", "dislike"])
    wants_more = any(token in text for token in ["增加", "更多", "喜欢", "很好", "more", "like"])
    mentions_ads = any(token in text for token in ["广告", "advertising", "ad ", "ads"])
    mentions_marketing = any(token in text for token in ["营销", "marketing", "品牌", "brand"])
    mentions_model_tech = any(token in text for token in ["模型", "参数", "benchmark", "基准", "技术"])

    if mentions_model_tech and wants_less:
        blocked_topics.append("pure model benchmark")

    if mentions_ads:
        preferred_topics.append("AI Advertising")
        category = "AI Advertising"
    elif mentions_marketing:
        preferred_topics.append("AI Marketing")
        category = "AI Marketing"
    elif mentions_model_tech:
        category = "AI Industry Trend"

    if wants_more and (mentions_ads or mentions_marketing):
        feedback_type = "adjustment" if wants_less else "positive"
        preference_change = "increase"
    elif wants_less:
        feedback_type = "negative"
        preference_change = "reduce"
    elif wants_more:
        feedback_type = "positive"
        preference_change = "increase"

    return {
        "feedback_type": feedback_type,
        "category": category,
        "preference_change": preference_change,
        "reason": "classified by local heuristic",
        "preferred_topics": preferred_topics,
        "blocked_topics": blocked_topics,
        "analysis_preference": "",
        "raw_feedback": feedback_text,
    }


def _extract_json(raw_response: str) -> str:
    content = raw_response.strip()
    if content.startswith("```"):
        lines = content.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        content = "\n".join(lines).strip()

    start = content.find("{")
    end = content.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("no JSON object found")
    return content[start : end + 1]


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _default_feedback(reason: str) -> dict[str, Any]:
    return {
        "feedback_type": "adjustment",
        "category": "Other",
        "preference_change": "adjust",
        "reason": reason,
        "preferred_topics": [],
        "blocked_topics": [],
        "analysis_preference": "",
        "raw_feedback": "",
    }
