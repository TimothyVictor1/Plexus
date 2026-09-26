"""Deterministic process mining (spec 02).

A directly-follows graph plus a heuristic dependency measure, in plain Python. The model is
used only to name things, and never alters the structure this file produces.
"""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from itertools import pairwise

from core.events.model import PlexusEvent


@dataclass
class Case:
    case_id: str
    events: list[PlexusEvent] = field(default_factory=list)

    @property
    def trace(self) -> tuple[str, ...]:
        return tuple(e.verb for e in sorted(self.events, key=lambda e: e.ts))

    @property
    def duration_s(self) -> float:
        if len(self.events) < 2:
            return 0.0
        times = sorted(e.ts for e in self.events)
        return (times[-1] - times[0]).total_seconds()


@dataclass
class Step:
    name: str
    verb: str
    frequency: int
    median_duration_s: float
    actors: list[str]
    ordinal: int


@dataclass
class Edge:
    source: str
    target: str
    count: int
    median_gap_s: float
    dependency: float


Metrics = dict[str, float | int | str]


@dataclass
class Bottleneck:
    """The single longest wait in a process, as the transition it actually is."""

    source: str
    target: str
    median_gap_s: float
    count: int


@dataclass
class DiscoveredProcess:
    process_id: str
    name: str
    steps: list[Step]
    edges: list[Edge]
    metrics: Metrics
    case_count: int
    variants: list[tuple[tuple[str, ...], int]]
    bottleneck: Bottleneck | None


class UnionFind:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def build_cases(events: list[PlexusEvent], correlation_key: str = "case") -> list[Case]:
    """Group events into cases by shared object ids.

    Events are connected when they touch a common object, so a thread that produces a task
    which produces an invoice becomes one case without anybody declaring a case id.
    """
    uf = UnionFind()
    for event in events:
        keys = [o.qualified for o in event.objects]
        anchor = f"event:{event.event_id}"
        uf.find(anchor)
        for key in keys:
            uf.union(anchor, key)
        for key in keys[1:]:
            uf.union(keys[0], key)

    buckets: dict[str, list[PlexusEvent]] = defaultdict(list)
    for event in events:
        anchor = f"event:{event.event_id}"
        buckets[uf.find(anchor)].append(event)

    cases = [Case(case_id=k, events=v) for k, v in buckets.items() if len(v) >= 2]
    cases.sort(key=lambda c: min(e.ts for e in c.events))
    return cases


def mine(cases: list[Case], process_id: str, name: str, min_edge: int = 2) -> DiscoveredProcess:
    follows: Counter[tuple[str, str]] = Counter()
    gaps: dict[tuple[str, str], list[float]] = defaultdict(list)
    verb_count: Counter[str] = Counter()
    verb_actors: dict[str, set[str]] = defaultdict(set)
    first_seen: dict[str, list[int]] = defaultdict(list)

    for case in cases:
        ordered = sorted(case.events, key=lambda e: e.ts)
        for idx, event in enumerate(ordered):
            verb_count[event.verb] += 1
            verb_actors[event.verb].add(event.actor.token)
            first_seen[event.verb].append(idx)
        for a, b in pairwise(ordered):
            if a.verb == b.verb:
                continue
            follows[(a.verb, b.verb)] += 1
            gaps[(a.verb, b.verb)].append((b.ts - a.ts).total_seconds())

    edges: list[Edge] = []
    for (src, dst), count in follows.items():
        if count < min_edge:
            continue
        reverse = follows.get((dst, src), 0)
        # Heuristic-miner dependency measure: near 1 means a genuine ordering, near 0 noise.
        dependency = (count - reverse) / (count + reverse + 1)
        if dependency <= 0.25:
            continue
        edges.append(
            Edge(src, dst, count, statistics.median(gaps[(src, dst)]), round(dependency, 3))
        )

    kept_verbs = {v for e in edges for v in (e.source, e.target)}
    if not kept_verbs:
        kept_verbs = set(verb_count)

    order = {v: statistics.median(first_seen[v]) for v in kept_verbs}
    steps = [
        Step(
            name=verb.replace("_", " ").capitalize(),
            verb=verb,
            frequency=verb_count[verb],
            median_duration_s=statistics.median(
                [g for (s, _), gs in gaps.items() if s == verb for g in gs] or [0.0]
            ),
            actors=sorted(verb_actors[verb]),
            ordinal=i,
        )
        for i, verb in enumerate(sorted(kept_verbs, key=lambda v: order[v]))
    ]

    durations = [c.duration_s for c in cases if c.duration_s > 0]
    traces = Counter(c.trace for c in cases)
    slowest = max(edges, key=lambda e: e.median_gap_s) if edges else None
    bottleneck = (
        Bottleneck(slowest.source, slowest.target, slowest.median_gap_s, slowest.count)
        if slowest
        else None
    )

    metrics: Metrics = {
        "median_cycle_time_s": round(statistics.median(durations), 1) if durations else 0.0,
        "mean_cycle_time_s": round(statistics.fmean(durations), 1) if durations else 0.0,
        "case_count": len(cases),
        "variant_count": len(traces),
        "step_count": len(steps),
        "bottleneck_from": bottleneck.source if bottleneck else "",
        "bottleneck_to": bottleneck.target if bottleneck else "",
        "bottleneck_gap_s": round(bottleneck.median_gap_s, 1) if bottleneck else 0.0,
        "events": sum(verb_count.values()),
    }

    return DiscoveredProcess(
        process_id=process_id,
        name=name,
        steps=steps,
        edges=sorted(edges, key=lambda e: -e.count),
        metrics=metrics,
        case_count=len(cases),
        variants=traces.most_common(8),
        bottleneck=bottleneck,
    )
