"""Convenções temporais aprovadas na fase 1; não calcula métricas."""

from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


DISPLAY_TIMEZONE = "America/Sao_Paulo"
POLICY_VERSION = 1


def utc_instant(value: str | datetime) -> datetime:
    instant = datetime.fromisoformat(value) if isinstance(value, str) else value
    if not isinstance(instant, datetime) or instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("Data sem fuso ou inválida.")
    return instant.astimezone(timezone.utc)


@dataclass(frozen=True)
class SprintWindow:
    state: str
    availability: str
    start: datetime | None = None
    end: datetime | None = None
    reason: str | None = None

    def contains(self, value: str | datetime) -> bool | None:
        if self.availability != "available":
            return None
        return self.start <= utc_instant(value) < self.end

    def as_dict(self) -> dict:
        return {"state": self.state, "availability": self.availability,
                "start_utc": self.start.isoformat() if self.start else None,
                "end_utc": self.end.isoformat() if self.end else None,
                "partial": self.state == "active", "reason": self.reason,
                "bounds": "[start,end)", "policy_version": POLICY_VERSION,
                "display_timezone": DISPLAY_TIMEZONE}


def sprint_window(sprint: dict, as_of: str | datetime) -> SprintWindow:
    state = sprint.get("state", "unknown")
    if state == "future":
        return SprintWindow(state, "not_started", reason="future_sprint")
    if state not in ("closed", "active"):
        return SprintWindow(state, "unavailable", reason="unsupported_state")
    if not sprint.get("startDate"):
        return SprintWindow(state, "unavailable", reason="missing_start_date")
    if state == "closed" and not sprint.get("completeDate"):
        return SprintWindow(state, "unavailable", reason="missing_complete_date")
    try:
        cutoff = utc_instant(as_of)
        start = utc_instant(sprint["startDate"])
        end = utc_instant(sprint["completeDate"]) if state == "closed" else cutoff
    except (ValueError, TypeError):
        return SprintWindow(state, "unavailable", reason="invalid_or_naive_date")
    if end <= start:
        return SprintWindow(state, "unavailable", reason="nonpositive_interval")
    if end > cutoff:
        return SprintWindow(state, "unavailable", reason="completion_after_collection")
    return SprintWindow(state, "available", start, end)


def display_instant(value: str | datetime) -> str:
    return utc_instant(value).astimezone(ZoneInfo(DISPLAY_TIMEZONE)).isoformat()
