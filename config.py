from dataclasses import dataclass
import os

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Settings:
    sources_file: str = os.getenv("SOURCES_FILE", "sources.yaml")
    news_lookback_days: int = int(os.getenv("NEWS_LOOKBACK_DAYS", "3"))
    max_items_per_source: int = int(os.getenv("MAX_ITEMS_PER_SOURCE", "20"))
    rss_timeout_seconds: int = int(os.getenv("RSS_TIMEOUT_SECONDS", "15"))
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    model_name: str = os.getenv("MODEL_NAME", "gpt-4o-mini")
    max_llm_analysis_items: int = int(os.getenv("MAX_LLM_ANALYSIS_ITEMS", "5"))
    max_discovery_results: int = int(os.getenv("MAX_DISCOVERY_RESULTS", "10"))
    max_daily_news_items: int = int(os.getenv("MAX_DAILY_NEWS_ITEMS", "5"))
    report_title: str = os.getenv("REPORT_TITLE", "AI Business Application Intelligence Report")
    preference_file: str = os.getenv("PREFERENCE_FILE", "outputs/preferences/user_preferences.json")
    feishu_webhook_url: str = os.getenv("FEISHU_WEBHOOK_URL", "")
    feishu_timeout_seconds: int = int(os.getenv("FEISHU_TIMEOUT_SECONDS", "10"))
    schedule_time: str = os.getenv("SCHEDULE_TIME", "09:00")
    report_output_dir: str = os.getenv("REPORT_OUTPUT_DIR", "outputs/reports")
    log_output_dir: str = os.getenv("LOG_OUTPUT_DIR", "outputs/logs")
    news_memory_path: str = os.getenv("NEWS_MEMORY_PATH", "outputs/history/news_memory.json")
    news_memory_days: int = int(os.getenv("NEWS_MEMORY_DAYS", "90"))


settings = Settings()
