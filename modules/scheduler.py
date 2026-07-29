from __future__ import annotations

from pathlib import Path


def build_cron_entry(
    project_root: str,
    schedule_time: str = "09:00",
    python_path: str = ".venv/bin/python",
) -> str:
    hour, minute = _parse_schedule_time(schedule_time)
    root = Path(project_root).resolve()
    command = f"cd '{root}' && {python_path} main.py >> outputs/logs/cron.log 2>&1"
    return f"{minute} {hour} * * * {command}"


def print_cron_setup(project_root: str = ".", schedule_time: str = "09:00") -> None:
    print("Add this line to your crontab with `crontab -e`:")
    print(build_cron_entry(project_root=project_root, schedule_time=schedule_time))


def _parse_schedule_time(schedule_time: str) -> tuple[str, str]:
    parts = schedule_time.strip().split(":")
    if len(parts) != 2:
        raise ValueError("SCHEDULE_TIME must use HH:MM format")
    hour = int(parts[0])
    minute = int(parts[1])
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError("SCHEDULE_TIME hour/minute out of range")
    return str(hour), str(minute)


if __name__ == "__main__":
    print_cron_setup()
