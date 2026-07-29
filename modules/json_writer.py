from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_json(
    data: Any,
    output_path: str = "outputs/analysis_results.json",
) -> str:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)
