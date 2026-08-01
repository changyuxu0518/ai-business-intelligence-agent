# AI Business Trend Daily Agent

This MVP fetches recent RSS news, analyzes selected items with an LLM, ranks them by business importance, learns simple user preferences from feedback, generates a Markdown daily business intelligence report, archives reports, and optionally delivers them to Feishu.

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## Environment Variables

RSS configuration:

- `NEWS_LOOKBACK_DAYS`: recent news window, default `3`.
- `MAX_ITEMS_PER_SOURCE`: maximum RSS entries read per source, default `20`.
- `RSS_TIMEOUT_SECONDS`: timeout for each RSS request, default `15`.
- `SOURCES_FILE`: RSS source config path, default `sources.yaml`.

LLM configuration:

- `OPENAI_API_KEY`: required for LLM analysis.
- `MODEL_NAME`: OpenAI model name, default `gpt-4o-mini`.
- `MAX_LLM_ANALYSIS_ITEMS`: maximum number of RSS items sent to the LLM, default `5`.

Ranking, report, and preference configuration:

- `MAX_DAILY_NEWS_ITEMS`: maximum qualified cases in the report, default `3`.
  It is an upper bound only; the agent never adds weaker items to reach it.
- `REPORT_TITLE`: Markdown report title, default `AI Business Trend Daily`.
- `PREFERENCE_FILE`: user preference JSON path, default `outputs/preferences/user_preferences.json`.
- `REPORT_OUTPUT_DIR`: historical report directory, default `outputs/reports`.
- `LOG_OUTPUT_DIR`: delivery log directory, default `outputs/logs`.
- `NEWS_MEMORY_PATH`: historical reported-news memory file, default `outputs/history/news_memory.json`.
- `NEWS_MEMORY_DAYS`: number of days retained in news memory, default `90`.

Feishu configuration:

- `FEISHU_WEBHOOK_URL`: optional Feishu bot webhook URL.
- `FEISHU_TIMEOUT_SECONDS`: Feishu request timeout, default `10`.

Scheduling configuration:

- `SCHEDULE_TIME`: daily run time in `HH:MM`, default `09:00`.

Do not commit `.env` or API keys.

## Run Once

```bash
source .venv/bin/activate
python main.py
```

The script runs this pipeline:

```text
RSS Fetch Layer
↓
AI Relevance Filtering Layer
↓
LLM Analysis Layer
↓
Historical Memory Deduplication Layer
↓
User Preference Adjustment
↓
News Ranking Layer
↓
Commercial AI Qualification Filter
↓
Daily Report Generator
↓
Historical Report Archive
↓
Optional Feishu Delivery
↓
Delivery Logging
```

## AI Relevance Filtering

The relevance gate runs before LLM business analysis. It filters generic market,
stock-price, and finance coverage that has no AI business-application signal, so
those articles neither consume analysis capacity nor dilute the daily report.

Items scoring 3 or above are analyzed. Explicit enterprise AI workflows score
higher; important AI model launches, regulation, and ecosystem changes are kept
as `ai_industry` even when they are not enterprise application cases. The delivery
log records both `relevance_filtered_items` and `low_quality_removed` for review.

After ranking and before report generation, the final Commercial AI Qualification
Filter requires a named enterprise or brand, a concrete AI application scenario,
and a known business impact. Otherwise it is discarded rather than rendered with
an "unknown", "Other", or "unable to confirm" placeholder. The report generator
repeats this validation as a defensive boundary.

The final count may be lower than `MAX_DAILY_NEWS_ITEMS`. Qualification rejects
are written with `title`, `discard_reason`, and ranking `score` to:

```text
outputs/logs/commercial_ai_discard_log.json
```

Stock-price coverage, funding, executive changes, lock-up periods, company
registrations, and generic AI-investment stories are removed unless the source
also provides a complete, concrete AI application and demonstrated business
impact.

## Scheduling

Generate a simple cron entry:

```bash
python -m modules.scheduler
```

Add the printed line to your crontab with:

```bash
crontab -e
```

## Outputs

Full analysis results are written to:

```text
outputs/analysis_results.json
```

Ranked top news items are written to:

```text
outputs/ranked_news.json
```

Historical reports are written to:

```text
outputs/reports/daily_report_YYYY-MM-DD.md
```

Delivery logs are written to:

```text
outputs/logs/YYYY-MM-DD_delivery.json
outputs/logs/delivery_log.json
```

User preferences are stored in:

```text
outputs/preferences/user_preferences.json
```

Historical news memory (only items selected for a daily report) is stored in:

```text
outputs/history/news_memory.json
```

## Historical Memory & Deduplication Monitoring

Deduplication reads both the JSON memory and every Markdown report under
`outputs/reports/`. Archived reports are parsed into title, company, event type,
topic, and topic-keyword fingerprints. An exact URL match is removed immediately;
items from the same company are filtered when their topic/event fingerprints are
highly similar, with an LLM comparison available for borderline semantic matches. It keeps
meaningful lifecycle progress—such as a new customer, market, business result,
product capability, or partner—and filters only unchanged event coverage.

Every filtered item is recorded in the deduplication log, including the matched
historical title and the decision reason:

```text
outputs/logs/dedup_log.json
```

The log is created automatically, retains 90 days of records, and can be used
alongside `outputs/logs/delivery_log.json` to review duplicate-removal volume,
selection volume, and the current memory size.

Example preference feedback:

```text
减少技术模型新闻，增加AI广告案例
```

## Notes

If `.env` is missing or `OPENAI_API_KEY` is empty, the app logs a clear error and exits before calling the LLM. If `FEISHU_WEBHOOK_URL` is missing, the report is still generated and Feishu delivery is skipped.
