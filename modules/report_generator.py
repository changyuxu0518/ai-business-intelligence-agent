from __future__ import annotations

from datetime import date
from pathlib import Path
import re
from typing import Any

from modules.commercial_ai_filter import (
    commercial_ai_application,
    commercial_ai_business_impact,
    commercial_ai_company,
    is_commercial_ai_qualified,
)


def generate_daily_report(
    ranked_results: list[dict[str, Any]],
    executive_summary: str,
    report_title: str = "AI Business Trend Daily",
    report_date: date | None = None,
) -> str:
    # Keep direct callers safe while allowing classified potential and explicit
    # empty-result fallback items selected by the main pipeline.
    ranked_results = [item for item in ranked_results if _is_reportable_item(item)]
    if not ranked_results:
        executive_summary = "今日未发现值得重点关注的 AI 商业应用趋势。"
    current_date = report_date or date.today()
    lines = [
        f"# {report_title}",
        "",
        f"Date: {current_date.isoformat()}",
        "",
        "## 执行摘要",
        "",
        executive_summary.strip() or "今日未发现值得重点关注的 AI 商业应用趋势。",
        "",
    ]

    if not ranked_results:
        lines.extend(["今日未发现值得重点关注的 AI 商业应用趋势。", ""])
    else:
        sections = [
            ("## 今日AI商业应用案例", "enterprise_application"),
            ("## AI商业趋势", "business_trend"),
            ("## AI行业关键动态", "ai_industry"),
        ]
        index = 1
        for heading, category in sections:
            section_items = [
                item for item in ranked_results
                if item.get("news", {}).get("candidate_category", "business_trend") == category
            ]
            if not section_items:
                continue
            lines.extend([heading, ""])
            for item in section_items:
                lines.extend(_render_news_item(index, item))
                index += 1

    lines.extend([
        "## 商业影响与思考",
        "",
        *_render_key_takeaways(ranked_results),
        "",
    ])

    return "\n".join(lines).rstrip() + "\n"


def write_daily_report(markdown: str, output_path: str = "outputs/daily_report.md") -> str:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown, encoding="utf-8")
    return str(path)


def _render_news_item(index: int, item: dict[str, Any]) -> list[str]:
    news = item.get("news", {})
    analysis = item.get("analysis", {})
    title = _safe_text(_text(analysis.get("title")) or _text(news.get("title")) or "未命名新闻")
    source = _safe_text(_text(analysis.get("source")) or _text(news.get("source")) or "未知来源")
    url = _text(analysis.get("url")) or _text(news.get("url"))
    category = _text(analysis.get("category")) or "其他"
    what_happened = _safe_text(_text(news.get("description")) or _text(analysis.get("summary")) or "新闻未提供足够事实描述。")
    company = _safe_text(commercial_ai_company(item))
    industry = _text(analysis.get("industry")) or "未明确"
    ai_application = commercial_ai_application(item)
    business_problem = _text(analysis.get("business_problem"))
    why_now = _text(analysis.get("why_now")) or "现有信息未充分说明这一变化的直接触发因素。"
    before_ai = _text(analysis.get("before_ai"))
    after_ai = _text(analysis.get("after_ai"))
    business_impact = commercial_ai_business_impact(item)
    competitive_implication = _text(analysis.get("competitive_implication")) or "同行应持续观察该变化是否重塑客户预期、流程标准或竞争门槛。"
    product_opportunity = _text(analysis.get("product_opportunity")) or _text(analysis.get("takeaway"))
    strategic_question = _text(analysis.get("strategic_question")) or "需要哪些证据，才能证明该 AI 应用创造了可持续的商业价值？"

    source_line = f"来源：[{source}]({url})" if url else f"来源：{source}"

    return [
        f"# {index}. {title}",
        "",
        source_line,
        "",
        f"分类：{_safe_text(category)}",
        "",
        f"企业/品牌：{company}",
        "",
        "## 发生了什么",
        "",
        what_happened,
        "",
        "## 为什么现在重要",
        "",
        why_now,
        "",
        "## 商业影响",
        "",
        business_impact,
        "",
        "## AI改变了什么业务流程",
        "",
        f"AI应用场景：{ai_application}\n\nAI介入前：{before_ai}\n\nAI介入后：{after_ai}",
        "",
        "## 竞争启示",
        "",
        competitive_implication,
        "",
        "## 产品机会",
        "",
        product_opportunity,
        "",
        "## 战略问题",
        "",
        strategic_question,
        "",
        "---",
        "",
    ]


def _render_key_takeaways(ranked_results: list[dict[str, Any]]) -> list[str]:
    if not ranked_results:
        return ["- 今日未发现值得重点关注的 AI 商业应用趋势。"]

    takeaways = []
    seen = set()
    for item in ranked_results:
        takeaway = _text(item.get("analysis", {}).get("takeaway"))
        if takeaway and takeaway not in seen:
            seen.add(takeaway)
            takeaways.append(f"- {takeaway}")
        if len(takeaways) >= 5:
            break

    if not takeaways:
        return ["- 持续关注企业 AI 应用是否带来可衡量的业务、产品或市场行为变化。"]
    return takeaways


def _is_reportable_item(item: dict[str, Any]) -> bool:
    status = str(item.get("commercial_ai_status", ""))
    if status in {"confirmed", "potential"}:
        return True
    if item.get("selected_as_fallback") is True:
        return True
    return is_commercial_ai_qualified(item)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _safe_text(value: str) -> str:
    value = re.sub(r"<(script|style|iframe|figure)[^>]*>.*?</\1>", " ", value, flags=re.IGNORECASE | re.DOTALL)
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", value)
    return " ".join(value.split())


def build_daily_report_path(output_dir: str = "outputs/reports", report_date: date | None = None) -> str:
    current_date = report_date or date.today()
    return str(Path(output_dir) / f"daily_report_{current_date.isoformat()}.md")
