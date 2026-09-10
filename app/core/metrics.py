from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from time import perf_counter
from typing import Final

MetricLabels = tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class CounterSample:
    name: str
    value: int
    labels: dict[str, str]


@dataclass(frozen=True)
class TimingSample:
    name: str
    count: int
    total_seconds: float
    max_seconds: float
    labels: dict[str, str]


_COUNTERS: Final[defaultdict[tuple[str, MetricLabels], int]] = defaultdict(int)
_TIMINGS: Final[defaultdict[tuple[str, MetricLabels], list[float]]] = defaultdict(
    lambda: [0.0, 0.0, 0.0]
)


def _labels_key(labels: dict[str, str] | None) -> MetricLabels:
    return tuple(sorted((labels or {}).items()))


def increment(
    name: str,
    value: int = 1,
    *,
    labels: dict[str, str] | None = None,
) -> None:
    if value < 1:
        return

    _COUNTERS[(name, _labels_key(labels))] += value


def observe_seconds(
    name: str,
    seconds: float,
    *,
    labels: dict[str, str] | None = None,
) -> None:
    if seconds < 0:
        return

    sample = _TIMINGS[(name, _labels_key(labels))]
    sample[0] += 1
    sample[1] += seconds
    sample[2] = max(sample[2], seconds)


@contextmanager
def timed(name: str, *, labels: dict[str, str] | None = None) -> Iterator[None]:
    started_at = perf_counter()
    try:
        yield
    finally:
        observe_seconds(name, perf_counter() - started_at, labels=labels)


def snapshot() -> dict[str, list[CounterSample] | list[TimingSample]]:
    counters = [
        CounterSample(name=name, value=value, labels=dict(labels))
        for (name, labels), value in sorted(_COUNTERS.items())
    ]
    timings = [
        TimingSample(
            name=name,
            count=int(values[0]),
            total_seconds=values[1],
            max_seconds=values[2],
            labels=dict(labels),
        )
        for (name, labels), values in sorted(_TIMINGS.items())
    ]
    return {"counters": counters, "timings": timings}


def reset() -> None:
    _COUNTERS.clear()
    _TIMINGS.clear()
