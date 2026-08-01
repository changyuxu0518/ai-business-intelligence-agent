from __future__ import annotations

import json
from typing import Any

from openai import OpenAI
from modules.relevance_filter import infer_company_from_text


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

APPLICATION_AREAS = {
    "Advertising",
    "Marketing",
    "Product",
    "Consumer Experience",
    "Enterprise Productivity",
    "Content Creation",
    "Regulation",
    "Industry Infrastructure",
    "Other",
}


class LLMClientError(Exception):
    """Raised when LLM configuration or API calls fail."""


class LLMClient:
    def __init__(self, api_key: str, model_name: str) -> None:
        if not api_key:
            raise LLMClientError("OPENAI_API_KEY is missing")
        if not model_name:
            raise LLMClientError("MODEL_NAME is missing")

        self.model_name = model_name
        self._client = OpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com"
)

    def analyze(self, news_item: dict[str, str]) -> dict[str, Any]:
        prompt = _build_prompt(news_item)
        raw_response = self._call_llm(prompt)
        analysis = _parse_analysis(raw_response)
        if str(analysis.get("company", "")).strip().lower() in {"", "unknown", "未明确"}:
            inferred_company = infer_company_from_text(news_item.get("title", ""), news_item.get("summary", ""))
            if inferred_company:
                analysis["company"] = inferred_company
        # RSS metadata is authoritative; do not depend on the model to reproduce it.
        analysis["title"] = news_item.get("title", "")
        analysis["source"] = news_item.get("source", "")
        analysis["url"] = news_item.get("link", "")
        return analysis

    def judge_news_duplicate(
        self, historical_news: dict[str, str], current_news: dict[str, str]
    ) -> dict[str, Any]:
        """Decide whether two reports describe one unchanged business event."""
        raw_response = self._call_llm(_build_duplicate_check_prompt(historical_news, current_news))
        try:
            parsed = json.loads(_extract_json(raw_response))
        except (json.JSONDecodeError, ValueError) as exc:
            raise LLMClientError("LLM returned invalid duplicate decision") from exc
        if not isinstance(parsed, dict):
            raise LLMClientError("LLM duplicate decision is not an object")
        return {
            "duplicate": _parse_boolean(parsed.get("duplicate", False)),
            "reason": str(parsed.get("reason", "") or ""),
        }

    def _call_llm(self, prompt: str) -> str:
        try:
            response = self._client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are an AI Business Analyst and News Editor for AI product managers. "
                            "Return valid JSON only. Do not use Markdown."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
            )
        except Exception as exc:
            raise LLMClientError("LLM API request failed") from exc

        content = response.choices[0].message.content
        if not content:
            raise LLMClientError("LLM returned empty content")
        return content


def analyze_news_items(news_items: list[dict[str, str]], llm_client: LLMClient) -> list[dict[str, Any]]:
    results = []
    for item in news_items:
        try:
            analysis = llm_client.analyze(item)
        except LLMClientError as exc:
            analysis = _error_analysis(str(exc))
        results.append(
            {
                "news": _format_news(item),
                "analysis": analysis,
            }
        )
    return results


def _build_prompt(news_item: dict[str, str]) -> str:
    return f"""
Analyze this RSS news item as an AI Business Analyst writing an "AI Business Application Intelligence Report" for product managers.

The report tracks how real enterprises and brands use AI to change business processes, customer experiences, and business models. It does not primarily track how AI companies, models, chips, or benchmarks develop.

Analyze:
1. Which enterprise, brand, or organization uses AI, and in which concrete business scenario.
2. The original business workflow or problem, and the specific step AI changes.
3. Why the enterprise needs this capability now, and the impact on users, employees, industry peers, revenue, cost, or competitive advantage.
4. What peer enterprises and AI product managers can learn, including a concrete product opportunity and a strategic question.
5. Why this change is happening now, how AI changes a specific workflow from before to after, and what competitors must reconsider.

Rules:
- Use only the provided news fields.
- Do not invent facts.
- Do not invent factual claims or metrics. However, when a named company and AI business scenario are stated, provide a clearly framed qualitative business analysis based on the stated facts and general business logic. For example, AI customer service can change service-cost structure, response workflow, and customer operations; do not say "现有信息无法确认" merely because exact metrics are absent.
- Copy title, source, and url exactly from the provided news fields.
- Write every analysis field in Simplified Chinese. Keep company names and product names in their official language when appropriate.
- Avoid technical detail dumping.
- Return JSON only.
- Do not use Markdown.
- Choose exactly one category.
- importance_score must be an integer from 1 to 5.
- ai_relevance_score must be an integer from 1 to 5: 5 = explicit AI application or business change; 4 = enterprise AI strategy/adoption; 3 = AI industry trend; 2 = weak AI connection; 1 = no AI connection.
- company, industry, and category must be filled whenever the title or description identifies them. If a named company such as Amazon, Google, Microsoft, Meta, or Apple appears, use that name; use "unknown" only when no company can be identified.
- When the headline starts with a named organization followed by an action (for example, "Abridge buys agentic AI company"), identify that organization as company even if the article does not identify the acquired company.
- ai_application_area must name a concrete business use case in Chinese, not a generic technology label. Good examples: "AI广告素材生成", "AI客户服务", "AI购物搜索助手", "AI销售自动化", "AI内容生产".
- ai_adoption_action must state the explicit action reported by the source, such as deploying, adopting, integrating, purchasing, or rolling out AI. Leave it empty if the source only discusses, funds, predicts, or invests in AI.
- business_scenario must identify the concrete department, user task, or operating workflow where AI is used. Leave it empty when the source does not provide one.
- event_type must be a short label such as adoption, deployment, integration, launch, acquisition, regulation, funding, stock_move, executive_change, or investment.
- topic_keywords must contain 3-8 concise company, product, and workflow keywords copied or directly derived from the source.
- before_ai and after_ai should describe workflows, costs, efficiency, or constraints; they must not make up metrics.
- strategic_question must be a single decision-relevant question, not a statement.
- why_now must explain the current trigger: technology maturity, cost pressure, consumer behavior, or competitive pressure.
- business_model_impact must explain the mechanism of change in cost structure, workflow ownership, user experience, or competitive advantage. Do not use "improve efficiency", "reduce cost", or "optimize experience" as a standalone conclusion.
- competitive_implication must state why peer companies should care.
- product_opportunity must identify a user pain point and a workflow that can be redesigned; do not merely suggest "build an AI product".
- Write business_model_impact with at least 100 Chinese characters and product_opportunity with at least 80 Chinese characters when the source provides enough evidence. Use conditional, qualitative reasoning for known workflows; state only the specific unknown fact when needed, rather than using generic "无法确认".
- A model launch, benchmark, GPU/chip update, AI-company funding round, or technical architecture update without a clear enterprise use case should receive a low score and have empty business-analysis fields where the news provides no evidence.
- An AI vendor's own model, feature, or product update is not a real enterprise application case unless the news shows a customer, brand, or non-AI business using it to change a workflow or customer experience. Score such vendor updates no higher than 3.

Category options:
AI Advertising, AI Marketing, AI Product, AI Consumer, AI Enterprise, AI Content Creation, AI Regulation, AI Industry Trend, Other

Importance score standard:
5 = a real enterprise or brand AI application case with explicit business value
4 = enterprise AI strategy or an industry adoption trend with plausible business impact
3 = AI tool or platform update that already has a stated business application
2 = technical AI progress without a clear application
1 = purely technical AI-industry news

News:
title: {news_item.get("title", "")}
source: {news_item.get("source", "")}
published_at: {news_item.get("published_at", "")}
category_hint: {news_item.get("category", "")}
url: {news_item.get("link", "")}
description: {news_item.get("summary", "")}

Return exactly this JSON schema:
{{
  "title": "",
  "source": "",
  "url": "",
  "company": "",
  "industry": "",
  "ai_application_area": "",
  "ai_adoption_action": "",
  "business_scenario": "",
  "event_type": "",
  "topic_keywords": [],
  "business_problem": "",
  "why_now": "",
  "before_ai": "",
  "after_ai": "",
  "user_behavior_change": "",
  "business_model_impact": "",
  "competitive_implication": "",
  "product_opportunity": "",
  "strategic_question": "",
  "category": "",
  "importance_score": 0,
  "ai_relevance_score": 0
}}
""".strip()


def _build_duplicate_check_prompt(
    historical_news: dict[str, str], current_news: dict[str, str]
) -> str:
    return f"""
Determine whether the current news item is a repeat of the same AI business event
already included in a previous daily report. Return valid JSON only:
{{"duplicate": true, "reason": ""}}.

Mark duplicate true only when these describe the same company, AI application
scenario, and business-event stage with no material new commercial progress.
Different headlines alone do not make an event new.

Mark duplicate false when the current item adds a new lifecycle stage or material
commercial development, including a new customer adoption, market entry, business
result, product capability, or partner. For example, a launch followed by first
enterprise customers is not a duplicate.

Historical news:
{json.dumps(historical_news, ensure_ascii=False)}

Current news:
{json.dumps(current_news, ensure_ascii=False)}
""".strip()


def _parse_analysis(raw_response: str) -> dict[str, Any]:
    try:
        parsed = json.loads(_extract_json(raw_response))
    except (json.JSONDecodeError, ValueError) as exc:
        return _error_analysis(f"LLM returned non-JSON content: {exc}")

    if not isinstance(parsed, dict):
        return _error_analysis("LLM JSON response is not an object")

    category = str(parsed.get("category", "Other") or "Other")
    if category not in CATEGORIES:
        category = "Other"

    application_area = str(parsed.get("ai_application_area", "") or "")

    analysis = {
        "title": str(parsed.get("title", "") or ""),
        "source": str(parsed.get("source", "") or ""),
        "url": str(parsed.get("url", "") or ""),
        "company": str(parsed.get("company", "") or ""),
        "industry": str(parsed.get("industry", "") or ""),
        "ai_application_area": application_area,
        "ai_adoption_action": str(parsed.get("ai_adoption_action", "") or ""),
        "business_scenario": str(parsed.get("business_scenario", "") or ""),
        "event_type": str(parsed.get("event_type", "") or ""),
        "topic_keywords": _parse_keywords(parsed.get("topic_keywords")),
        "business_problem": str(parsed.get("business_problem", "") or ""),
        "why_now": str(parsed.get("why_now", "") or ""),
        "before_ai": str(parsed.get("before_ai", "") or ""),
        "after_ai": str(parsed.get("after_ai", "") or ""),
        "user_behavior_change": str(parsed.get("user_behavior_change", "") or ""),
        "business_model_impact": str(parsed.get("business_model_impact", "") or ""),
        "competitive_implication": str(parsed.get("competitive_implication", "") or ""),
        "product_opportunity": str(parsed.get("product_opportunity", "") or ""),
        "strategic_question": str(parsed.get("strategic_question", "") or ""),
        "category": category,
        "importance_score": _parse_importance_score(parsed.get("importance_score")),
        "ai_relevance_score": _parse_importance_score(parsed.get("ai_relevance_score")),
    }
    # Preserve the legacy keys consumed by ranking and historical integrations.
    analysis.update(_legacy_analysis_fields(analysis))
    return analysis


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


def _parse_importance_score(value: Any) -> int:
    try:
        score = int(value)
    except (TypeError, ValueError):
        score = 1
    return max(1, min(score, 5))


def _parse_boolean(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes"}


def _parse_keywords(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()][:8]
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()][:8]
    return []


def _error_analysis(message: str) -> dict[str, Any]:
    analysis = {
        "title": "",
        "source": "",
        "url": "",
        "company": "",
        "industry": "",
        "ai_application_area": "Other",
        "ai_adoption_action": "",
        "business_scenario": "",
        "event_type": "",
        "topic_keywords": [],
        "business_problem": "",
        "why_now": "",
        "before_ai": "",
        "after_ai": "",
        "user_behavior_change": "",
        "business_model_impact": "",
        "competitive_implication": "",
        "product_opportunity": "",
        "strategic_question": "",
        "category": "Other",
        "importance_score": 1,
        "ai_relevance_score": 1,
    }
    analysis.update(_legacy_analysis_fields(analysis))
    analysis["error"] = message
    return analysis


def _legacy_analysis_fields(analysis: dict[str, Any]) -> dict[str, Any]:
    """Provide old analysis keys so unchanged ranking consumers continue to work."""
    return {
        "summary": "",
        "why_it_matters": str(analysis.get("business_problem", "") or ""),
        "key_points": [],
        "business_impact": str(analysis.get("business_model_impact", "") or ""),
        "takeaway": str(analysis.get("product_opportunity", "") or ""),
    }


def _format_news(news_item: dict[str, str]) -> dict[str, str]:
    return {
        "title": news_item.get("title", ""),
        "source": news_item.get("source", ""),
        "url": news_item.get("link", ""),
        "published": news_item.get("published_at", ""),
        "description": news_item.get("summary", ""),
        "candidate_category": news_item.get("candidate_category", "business_trend"),
        "source_type": news_item.get("source_type", "rss"),
        "company_role": news_item.get("company_role", "unknown"),
        "case_relevance_score": news_item.get("case_relevance_score", "1"),
    }


def generate_executive_summary(ranked_results: list[dict[str, Any]], llm_client: LLMClient) -> str:
    if not ranked_results:
        return "今日未发现值得重点关注的 AI 商业应用趋势。"

    prompt = _build_executive_summary_prompt(ranked_results)
    try:
        summary = llm_client._call_llm(prompt).strip()
    except LLMClientError:
        return _fallback_executive_summary(ranked_results)

    if not summary:
        return _fallback_executive_summary(ranked_results)
    return summary


def _build_executive_summary_prompt(ranked_results: list[dict[str, Any]]) -> str:
    items = []
    for index, item in enumerate(ranked_results, start=1):
        news = item.get("news", {})
        analysis = item.get("analysis", {})
        items.append(
            {
                "rank": index,
                "title": news.get("title", ""),
                "category": analysis.get("category", "Other"),
                "company": analysis.get("company", ""),
                "industry": analysis.get("industry", ""),
                "ai_application_area": analysis.get("ai_application_area", ""),
                "business_problem": analysis.get("business_problem", ""),
                "business_model_impact": analysis.get("business_model_impact", ""),
                "product_opportunity": analysis.get("product_opportunity", ""),
                "strategic_question": analysis.get("strategic_question", ""),
                "importance_score": analysis.get("importance_score", 1),
            }
        )

    return f"""
You are an AI Business Analyst writing the executive summary for an AI Business Application Intelligence Report read by AI product managers.

Synthesize the following ranked news items into one concise strategic overview.

Answer in Simplified Chinese: identify one core AI-business trend today, cite two representative cases, and state the implication for enterprises and product managers. Do not list or summarize every article.

Focus on AI application, business impact, product strategy, market changes, and consumer behavior.
Avoid simply repeating news titles. Avoid unsupported assumptions. Avoid excessive technical detail.

Return plain text only, in Simplified Chinese, 200-300 Chinese characters.

Ranked news items:
{json.dumps(items, ensure_ascii=False, indent=2)}
""".strip()


def _fallback_executive_summary(ranked_results: list[dict[str, Any]]) -> str:
    categories = []
    for item in ranked_results:
        category = item.get("analysis", {}).get("category", "Other")
        if category and category not in categories:
            categories.append(str(category))
    if not categories:
        return "今日 AI 商业应用信号较为分散，尚未出现单一主导趋势。"
    return (
        "今日 AI 商业应用信号主要集中在 "
        + ", ".join(categories[:3])
        + "。共同趋势是，AI 的价值越来越取决于企业落地、市场影响和产品执行，而非单纯的技术新颖性。"
    )
