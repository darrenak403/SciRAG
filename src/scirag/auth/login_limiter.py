"""Counts failed logins per (client IP, email) in memory.

Lives in the API process, so it resets on restart and is not shared between
instances. Enough for a single-instance deployment.
"""

import time

MAX_FAILURES = 5
WINDOW_SECONDS = 15 * 60
# Above this many tracked pairs, expired ones are swept so the table cannot grow forever.
SWEEP_ABOVE = 10_000

_failures: dict[tuple[str, str], list[float]] = {}


def _recent(key: tuple[str, str]) -> list[float]:
    cutoff = time.monotonic() - WINDOW_SECONDS
    recent = [moment for moment in _failures.get(key, []) if moment > cutoff]
    if recent:
        _failures[key] = recent
    else:
        _failures.pop(key, None)
    return recent


def is_blocked(ip: str, email: str) -> bool:
    return len(_recent((ip, email))) >= MAX_FAILURES


def record_failure(ip: str, email: str) -> None:
    if len(_failures) > SWEEP_ABOVE:
        for key in list(_failures):
            _recent(key)
    _failures.setdefault((ip, email), []).append(time.monotonic())


def clear(ip: str, email: str) -> None:
    _failures.pop((ip, email), None)


def reset() -> None:
    """Forget everything. Used by tests."""
    _failures.clear()
