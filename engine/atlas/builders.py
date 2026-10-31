"""Run every builder in dependency order."""
from __future__ import annotations

from .build import build_needle_people, build_seed
from .problems import Problem
from .store import Store


def build_all(store: Store, problem: Problem) -> dict:
    out = {}
    build_seed(store)
    out["needle_people"] = build_needle_people(store, problem)
    try:
        from .collectors.ted import build_ted
        out["ted"] = build_ted(store, problem)
    except ImportError:
        pass
    try:
        from .collectors.web import build_web
        out["web"] = build_web(store, problem)
    except ImportError:
        pass
    store.apply_curation()
    store.commit()
    out["stats"] = store.stats()
    return out
