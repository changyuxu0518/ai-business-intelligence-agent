from datetime import date

from config import settings
from modules.delivery_logger import build_delivery_log, write_delivery_log
from modules.case_verifier import verify_discovery_candidates
from modules.discovery_search import build_discovery_stats, discover_enterprise_ai_cases
from modules.feishu_sender import send_markdown_report
from modules.json_writer import write_json
from modules.llm_client import (
    LLMClient,
    LLMClientError,
    analyze_news_items,
    generate_executive_summary,
)
from modules.news_ranker import rank_news, summarize_ranked_news
from modules.news_memory import add_news_to_memory, check_duplicate_news, load_news_memory, write_dedup_log
from modules.preference_store import load_preferences
from modules.report_generator import (
    build_daily_report_path,
    generate_daily_report,
    write_daily_report,
)
from modules.rss_fetcher import build_rss_quality_stats, fetch_recent_news


def main() -> None:
    run_date = date.today().isoformat()
    log_record = build_delivery_log(run_date=run_date)

    try:
        news_items = fetch_recent_news(
            sources_file=settings.sources_file,
            lookback_days=settings.news_lookback_days,
            max_items_per_source=settings.max_items_per_source,
            timeout_seconds=settings.rss_timeout_seconds,
        )
        for item in news_items:
            item.setdefault("source_type", "rss")
            item.setdefault("company_role", "unknown")
            item.setdefault("case_relevance_score", "1")
        discovery_items = discover_enterprise_ai_cases(
            max_results=settings.max_discovery_results,
            lookback_days=settings.news_lookback_days,
        )
        verified_cases, verification_stats = verify_discovery_candidates(discovery_items)
        discovery_stats = build_discovery_stats(discovery_items)
        news_items.extend(discovery_items)
        news_items.sort(
            key=lambda item: (int(item.get("verification_score", "1")), int(item.get("case_relevance_score", "1")), item.get("published_at", "")),
            reverse=True,
        )
        print(
            "Discovery statistics: "
            f"retrieved: {discovery_stats['retrieved']} | "
            f"enterprise_application: {discovery_stats['enterprise_application']} | "
            f"ai_industry: {discovery_stats['ai_industry']} | "
            f"business_trend: {discovery_stats['business_trend']}"
        )
        print(f"Case verification statistics: Discovery candidates: {verification_stats['discovery_candidates']} | Verified enterprise cases: {verification_stats['verified_enterprise_cases']} | Rejected trend articles: {verification_stats['rejected_trend_articles']}")
        print("Top verified cases:")
        for case in verified_cases[:5]:
            print(f"- Company: {case['title']} | AI application: {case['summary'][:120]}")
        rss_stats = build_rss_quality_stats(news_items)
        rss_stats_path = write_json(rss_stats, "outputs/rss_quality_stats.json")
        candidate_counts = rss_stats["candidate_analysis"]
        print(
            "RSS candidate analysis: "
            f"Enterprise AI application: {candidate_counts['enterprise_application']} articles | "
            f"AI industry: {candidate_counts['ai_industry']} articles | "
            f"Business trend: {candidate_counts['business_trend']} articles"
        )
        print("Top 10 sources contributing articles:")
        for entry in rss_stats["top_sources"]:
            print(f"- {entry['source']}: {entry['articles']}")
        case_counts = rss_stats["case_discovery"]
        print(
            "Case discovery statistics: "
            f"enterprise_adopter: {case_counts['enterprise_adopter']} | "
            f"ai_provider: {case_counts['ai_provider']} | unknown: {case_counts['unknown']}"
        )
        print("Top enterprise AI cases:")
        for index, case in enumerate(rss_stats["top_enterprise_ai_cases"][:5], start=1):
            print(f"{index}. company: {case['company']} | AI application: {case['title']}")

        selected_items = news_items[: settings.max_llm_analysis_items]
        try:
            llm_client = LLMClient(
                api_key=settings.openai_api_key,
                model_name=settings.model_name,
            )
        except LLMClientError as exc:
            log_record["error"] = str(exc)
            write_delivery_log(log_record, settings.log_output_dir)
            print(str(exc))
            print("Create a .env file from .env.example and set OPENAI_API_KEY.")
            return

        preferences = load_preferences(settings.preference_file)
        analysis_results = analyze_news_items(selected_items, llm_client)
        _classify_analyzed_candidates(analysis_results)
        news_memory = load_news_memory(settings.news_memory_path, settings.news_memory_days)
        deduplicated_results = []
        duplicate_count = 0
        duplicate_results = []
        for item in analysis_results:
            duplicate_decision = check_duplicate_news(item, news_memory, llm_client)
            if duplicate_decision["duplicate"]:
                duplicate_count += 1
                duplicate_results.append({"item": item, "decision": duplicate_decision})
                print(f"Skipped historical duplicate: {item['news'].get('title', '')} ({duplicate_decision['reason']})")
                continue
            deduplicated_results.append(item)
        dedup_log_path = write_dedup_log(duplicate_results)

        ranked_results = rank_news(deduplicated_results, preferences)
        top_results = ranked_results[: settings.max_daily_news_items]
        executive_summary = generate_executive_summary(top_results, llm_client)

        analysis_output_path = write_json(analysis_results, "outputs/analysis_results.json")
        ranked_output_path = write_json(summarize_ranked_news(top_results), "outputs/ranked_news.json")
        report_markdown = generate_daily_report(
            ranked_results=top_results,
            executive_summary=executive_summary,
            report_title=settings.report_title,
        )
        report_output_path = write_daily_report(
            report_markdown,
            build_daily_report_path(settings.report_output_dir),
        )

        feishu_result = send_markdown_report(
            report_path=report_output_path,
            webhook_url=settings.feishu_webhook_url,
            timeout_seconds=settings.feishu_timeout_seconds,
        )
        feishu_sent = bool(feishu_result.get("ok"))
        delivery_error = ""
        if not feishu_sent and not feishu_result.get("skipped"):
            delivery_error = str(feishu_result.get("error", "Feishu delivery failed"))

        updated_memory = add_news_to_memory(
            top_results,
            news_memory,
            settings.news_memory_path,
            settings.news_memory_days,
        )

        log_record = build_delivery_log(
            run_date=run_date,
            report_generated=True,
            feishu_sent=feishu_sent,
            error=delivery_error,
            report_path=report_output_path,
            ranked_news_path=ranked_output_path,
            analysis_results_path=analysis_output_path,
            fetched_items=len(news_items),
            analyzed_items=len(analysis_results),
            duplicates_removed=duplicate_count,
            final_selected=len(top_results),
            memory_size=len(updated_memory),
        )
        log_paths = write_delivery_log(log_record, settings.log_output_dir)

        print(f"Fetched items: {len(news_items)}")
        print(f"Analyzed items: {len(analysis_results)}")
        print(f"Duplicates removed: {duplicate_count}")
        print(f"Selected items: {len(top_results)}")
        print(f"Memory size: {len(updated_memory)}")
        print(f"Saved analysis results to {analysis_output_path}.")
        print(f"Saved RSS quality stats to {rss_stats_path}.")
        print(f"Saved ranked news to {ranked_output_path}.")
        print(f"Saved daily report to {report_output_path}.")
        print(f"Saved delivery log to {log_paths['latest']}.")
        print(f"Saved dedup log to {dedup_log_path}.")
        if feishu_sent:
            print("Delivery status: sent")
        elif feishu_result.get("skipped"):
            print("Delivery status: skipped (FEISHU_WEBHOOK_URL is missing)")
        else:
            print(f"Delivery status: failed ({delivery_error})")

    except Exception as exc:
        log_record["error"] = f"Pipeline failed: {exc}"
        write_delivery_log(log_record, settings.log_output_dir)
        print(log_record["error"])


def _classify_analyzed_candidates(results: list[dict]) -> None:
    """Use AI relevance to classify and rank, never to discard business context."""
    for item in results:
        analysis = item.get("analysis", {})
        news = item.get("news", {})
        relevance = int(analysis.get("ai_relevance_score", 1))
        company = str(analysis.get("company", "")).strip().lower()
        has_application = bool(analysis.get("ai_application_area"))
        has_workflow_change = bool(analysis.get("after_ai") or analysis.get("business_problem"))
        if relevance >= 3 and company not in {"", "unknown", "未明确"} and has_application and has_workflow_change:
            news["candidate_category"] = "enterprise_application"
        elif relevance >= 3:
            news["candidate_category"] = "ai_industry"
        else:
            news["candidate_category"] = "business_trend"


if __name__ == "__main__":
    main()
