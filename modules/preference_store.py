from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_PREFERENCES: dict[str, Any] = {
    "preferred_categories": [],
    "reduced_categories": [],
    "blocked_topics": [],
    "preferred_topics": [],
    "analysis_preferences": [],
    "feedback_history": [],
}


def load_preferences(preference_file: str = "outputs/user_preferences.json") -> dict[str, Any]:
    path = Path(preference_file)
    if not path.exists():
        return DEFAULT_PREFERENCES.copy()

    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return DEFAULT_PREFERENCES.copy()

    if not isinstance(loaded, dict):
        return DEFAULT_PREFERENCES.copy()

    preferences = DEFAULT_PREFERENCES.copy()
    preferences.update(loaded)
    return preferences


def save_preferences(preferences: dict[str, Any], preference_file: str = "outputs/user_preferences.json") -> str:
    path = Path(preference_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(preferences, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def update_preferences(
    preferences: dict[str, Any],
    structured_feedback: dict[str, Any],
) -> dict[str, Any]:
    updated = DEFAULT_PREFERENCES.copy()
    updated.update(preferences or {})

    category = _text(structured_feedback.get("category") or structured_feedback.get("target"))
    change = _text(structured_feedback.get("preference_change") or structured_feedback.get("action"))

    if category and category != "Other":
        if change in {"increase", "more", "prefer"}:
            _append_unique(updated["preferred_categories"], category)
            _remove_value(updated["reduced_categories"], category)
        elif change in {"reduce", "less", "block"}:
            _append_unique(updated["reduced_categories"], category)
            _remove_value(updated["preferred_categories"], category)

    for topic in structured_feedback.get("preferred_topics", []) or []:
        _append_unique(updated["preferred_topics"], _text(topic))

    for topic in structured_feedback.get("blocked_topics", []) or []:
        _append_unique(updated["blocked_topics"], _text(topic))

    analysis_preference = _text(structured_feedback.get("analysis_preference"))
    if analysis_preference:
        _append_unique(updated["analysis_preferences"], analysis_preference)

    history = updated.setdefault("feedback_history", [])
    if isinstance(history, list):
        history.append(structured_feedback)

    return updated


def _append_unique(values: list[Any], value: str) -> None:
    if value and value not in values:
        values.append(value)


def _remove_value(values: list[Any], value: str) -> None:
    if value in values:
        values.remove(value)


def _text(value: Any) -> str:
    return str(value or "").strip()
