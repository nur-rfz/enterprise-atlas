"""Target companies.

A target is either a Python module in this package (``mercedes``) or a JSON file with the
same fields (see ``_template.json``). Select it with ``ATLAS_TARGET=<name|path.json>``.

Fields: COMPANY_ID, COMPANY_NAME, OBSERVED, LINKEDIN_COMPANIES, SOURCES, UNITS, STRUCTURE,
UNIT_PARENTS, BOARD, UNIT_LEXICON, EMPLOYER_PATTERNS.
"""
from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

DEFAULTS = dict(DEFAULT_UNIT=None, STALE_UNITS={}, UNIT_PRECEDENCE=[], OBSERVED="", LINKEDIN_COMPANIES={}, SOURCES={}, UNITS=[], STRUCTURE=[], UNIT_PARENTS={},
                BOARD=[], UNIT_LEXICON={}, EMPLOYER_PATTERNS=[])


def load(name: str) -> SimpleNamespace:
    p = Path(name)
    if not p.suffix:
        cand = Path(__file__).parent / f"{name}.json"
        if cand.exists():
            p = cand
    if p.suffix == ".json":
        data = {**DEFAULTS, **{k: v for k, v in json.loads(p.read_text()).items() if not k.startswith("$")}}
        data["UNITS"] = [tuple(u) for u in data["UNITS"]]
        data["STRUCTURE"] = [tuple(s) for s in data["STRUCTURE"]]
        data["BOARD"] = [tuple(b) for b in data["BOARD"]]
        data["UNIT_PRECEDENCE"] = [tuple(p) for p in data["UNIT_PRECEDENCE"]]
        return SimpleNamespace(**data)
    mod = importlib.import_module(f"{__name__}.{name}")
    return SimpleNamespace(**{**DEFAULTS, **{k: getattr(mod, k) for k in dir(mod) if k.isupper()}})


TARGET = load(os.environ.get("ATLAS_TARGET", "mercedes"))
