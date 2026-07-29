from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def send_markdown_report(
    report_path: str = "outputs/daily_report.md",
    webhook_url: str = "",
    timeout_seconds: int = 10,
) -> dict[str, Any]:
    if not webhook_url:
        return {"ok": False, "skipped": True, "error": "FEISHU_WEBHOOK_URL is missing"}

    path = Path(report_path)
    if not path.exists():
        return {"ok": False, "skipped": False, "error": f"report file not found: {report_path}"}

    content = path.read_text(encoding="utf-8")
    payload = {
        "msg_type": "text",
        "content": {
            "text": content,
        },
    }
    request = Request(
        webhook_url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            response_body = response.read().decode("utf-8")
    except HTTPError as exc:
        return {"ok": False, "skipped": False, "error": f"Feishu HTTP error: {exc.code}"}
    except (URLError, TimeoutError, OSError) as exc:
        return {"ok": False, "skipped": False, "error": f"Feishu request failed: {exc}"}

    return {"ok": True, "skipped": False, "response": response_body}
