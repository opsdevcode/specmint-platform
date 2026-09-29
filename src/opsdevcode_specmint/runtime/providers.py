"""Injected clock and attempt-id providers. Tests supply Static* fakes."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4


class Clock(Protocol):
    def now(self) -> datetime: ...


class AttemptIdProvider(Protocol):
    def next_id(self) -> str: ...


@dataclass(frozen=True, slots=True)
class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class UuidAttemptIds:
    def next_id(self) -> str:
        return str(uuid4())


@dataclass(frozen=True, slots=True)
class StaticClock:
    instant: datetime

    def now(self) -> datetime:
        return self.instant


@dataclass(slots=True)
class SequenceAttemptIds:
    values: Sequence[str]
    _index: int = field(default=0, init=False)

    def next_id(self) -> str:
        if self._index >= len(self.values):
            raise IndexError(
                "set SequenceAttemptIds.values to cover every attempt; the fixture ran out of ids"
            )
        value = self.values[self._index]
        self._index += 1
        return value
