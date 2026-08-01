from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


def build_delivery_log(
    run_date: str,
    report_generated: bool = False,
    feishu_sent: bool = False,
    error: str = "",
    report_path: str = "",
    ranked_news_path: str = "",
    analysis_results_path: str = "",
    fetched_items: int = 0,
    analyzed_items: int = 0,
    relevance_filtered_items: int = 0,
    low_quality_removed: int = 0,
    duplicates_removed: int = 0,
    final_selected: int = 0,
    memory_size: int = 0,
) -> dict[str, Any]:
    return {
        "date": run_date,
        "report_generated": report_generated,
        "feishu_sent": feishu_sent,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "error": error,
        "report_path": report_path,
        "ranked_news_path": ranked_news_path,
        "analysis_results_path": analysis_results_path,
        "fetched_items": fetched_items,
        "analyzed_items": analyzed_items,
        "relevance_filtered_items": relevance_filtered_items,
        "low_quality_removed": low_quality_removed,
        "duplicates_removed": duplicates_removed,
        "final_selected": final_selected,
        "memory_size": memory_size,
    }


def write_delivery_log(log_record: dict[str, Any], output_dir: str = "outputs/logs") -> dict[str, str]:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    run_date = str(log_record.get("date", "unknown"))
    dated_path = directory / f"{run_date}_delivery.json"
    latest_path = directory / "delivery_log.json"
    payload = json.dumps(log_record, ensure_ascii=False, indent=2)
    dated_path.write_text(payload, encoding="utf-8")
    latest_path.write_text(payload, encoding="utf-8")
    return {"dated": str(dated_path), "latest": str(latest_path)}
