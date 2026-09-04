"""Deterministic application clock boundaries (TST-008).

Wall-clock reads that decide a boundary go through :func:`now` instead of
calling ``datetime.now(UTC)`` inline, so a test can install an exact instant
and prove the ``==``, ``-1us`` and ``+1us`` outcomes without sleeping. Nothing
installs a clock in production, where :func:`now` *is* ``datetime.now(UTC)``.

Database-authoritative transactional timing is untouched: code that must read
the database's own clock keeps calling ``database_clock()`` and keeps capturing
exactly one reading per transaction.

Elapsed durations are deliberately not measured here. A wall clock may jump
backwards or forwards, so duration measurement uses ``time.monotonic()`` at the
measuring site rather than a difference of two wall-clock reads.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

Clock = Callable[[], datetime]

_installed: Clock | None = None


def now() -> datetime:
    """Return the current instant as an aware UTC datetime."""
    reader = _installed
    if reader is None:
        return datetime.now(UTC)
    value = reader()
    if value.tzinfo is None or value.utcoffset() is None:
        raise RuntimeError("the installed application clock returned a naive datetime")
    return value.astimezone(UTC)


@contextmanager
def use_clock(clock: Clock) -> Iterator[Clock]:
    """Install ``clock`` as the application clock for the duration of the block."""
    global _installed
    previous = _installed
    _installed = clock
    try:
        yield clock
    finally:
        _installed = previous
