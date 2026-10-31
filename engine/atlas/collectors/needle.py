"""Needle (needle.app) LinkedIn collector.

Needle exposes LinkedIn through a connected account. A non-Premium account gets roughly
100 people searches/day and 500/week (10 hits per page), so the harvester plans queries
from the problem definition instead of trying to enumerate 49k employees:

    for each LinkedIn company id of the target
        for each title keyword of the problem (warranty, Gewährleistung, after-sales data, ...)
            page through results until the page budget for that query is spent

Every response is stored verbatim as a raw document (collector="needle.people_search"),
and ``build_needle_people`` turns them into graph assertions.

The same raw format is produced by ``import_mcp_response`` so results pulled through the
Needle MCP server (e.g. from Claude) are ingested identically.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Iterator

import httpx

from ..problems import Problem
from ..store import Store

BASE_URL = os.environ.get("NEEDLE_BASE_URL", "https://needle.app/api/v1")
# Paths. The sales-navigator and search-parameter paths are documented in Needle's tool
# descriptions; override the others with env vars if Needle's REST docs differ.
PATHS = {
    "people_classic": os.environ.get("NEEDLE_PATH_PEOPLE_CLASSIC", "/linkedin/people/search"),
    "people_sales_nav": os.environ.get("NEEDLE_PATH_PEOPLE_SALES_NAV", "/linkedin/sales-navigator/people/search"),
    "jobs": os.environ.get("NEEDLE_PATH_JOBS", "/linkedin/jobs/search"),
    "job": os.environ.get("NEEDLE_PATH_JOB", "/linkedin/jobs/{job_id}"),
    "profile": os.environ.get("NEEDLE_PATH_PROFILE", "/linkedin/profiles/{identity}"),
    "company": os.environ.get("NEEDLE_PATH_COMPANY", "/linkedin/companies/{identifier}"),
    "params": "/linkedin/search/parameters",
}


class BudgetExhausted(RuntimeError):
    pass


@dataclass
class Budget:
    """Tracks Needle's remainingUsage and keeps a reserve for interactive use."""

    reserve_day: int = 10
    day: int | None = None
    week: int | None = None
    spent: int = 0

    def update(self, payload: dict) -> None:
        usage = payload.get("remainingUsage") or {}
        self.day = usage.get("day", self.day)
        self.week = usage.get("week", self.week)

    def check(self) -> None:
        if self.day is not None and self.day <= self.reserve_day:
            raise BudgetExhausted(f"Needle daily budget at {self.day}; keeping reserve of {self.reserve_day}.")
        if self.week is not None and self.week <= self.reserve_day:
            raise BudgetExhausted(f"Needle weekly budget at {self.week}.")


class NeedleClient:
    def __init__(self, api_key: str | None = None, connected_account_id: str | None = None,
                 base_url: str = BASE_URL, budget: Budget | None = None, pause_s: float = 1.5):
        self.api_key = api_key or os.environ.get("NEEDLE_API_KEY")
        self.account = connected_account_id or os.environ.get("NEEDLE_CONNECTED_ACCOUNT_ID")
        if not self.api_key:
            raise RuntimeError("NEEDLE_API_KEY is not set")
        if not self.account:
            raise RuntimeError("NEEDLE_CONNECTED_ACCOUNT_ID is not set")
        self.http = httpx.Client(base_url=base_url, timeout=60,
                                 headers={"Authorization": f"Bearer {self.api_key}", "content-type": "application/json"})
        self.budget = budget or Budget()
        self.pause_s = pause_s

    def _call(self, method: str, path: str, **kw) -> dict:
        self.budget.check()
        for attempt in range(4):
            r = self.http.request(method, path, **kw)
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(2 ** (attempt + 1))
                continue
            r.raise_for_status()
            data = r.json()
            self.budget.update(data)
            self.budget.spent += 1
            time.sleep(self.pause_s)
            return data
        r.raise_for_status()
        return {}

    def search_people(self, params: dict, sales_navigator: bool = False) -> dict:
        path = PATHS["people_sales_nav" if sales_navigator else "people_classic"]
        return self._call("POST", path, json={"connectedAccountId": self.account, **params})

    def search_jobs(self, params: dict) -> dict:
        return self._call("POST", PATHS["jobs"], json={"connectedAccountId": self.account, **params})

    def get_job(self, job_id: str) -> dict:
        return self._call("GET", PATHS["job"].format(job_id=job_id), params={"connectedAccountId": self.account})

    def get_profile(self, identity: str) -> dict:
        return self._call("GET", PATHS["profile"].format(identity=identity), params={"connectedAccountId": self.account})

    def get_company(self, identifier: str) -> dict:
        return self._call("GET", PATHS["company"].format(identifier=identifier), params={"connectedAccountId": self.account})

    def search_parameters(self, type: str, keywords: str, service: str = "classic") -> dict:
        return self._call("GET", PATHS["params"], params={"connectedAccountId": self.account, "type": type,
                                                          "keywords": keywords, "service": service})


# ------------------------------------------------------------------ planning
@dataclass
class PeopleQuery:
    label: str
    params: dict
    max_pages: int = 3


def plan_people_queries(problem: Problem, company_ids: list[str], max_pages: int = 3) -> list[PeopleQuery]:
    queries = []
    for title in problem.search_titles:
        queries.append(PeopleQuery(label=f"title:{title}", max_pages=max_pages,
                                   params={"companies": company_ids, "advancedKeywords": {"title": title}, "limit": 10}))
    return queries


def harvest_people(store: Store, client: NeedleClient, queries: list[PeopleQuery], log=print) -> dict:
    done = {r["request"] for r in store.db.execute("SELECT request FROM raw_documents WHERE collector='needle.people_search'")}
    stats = {"calls": 0, "hits": 0, "skipped_cached": 0, "stopped": None}
    try:
        for q in queries:
            cursor = None
            for page in range(q.max_pages):
                req = {"label": q.label, "page": page, "params": q.params}
                import json as _json
                if _json.dumps(req, default=str) in done:
                    stats["skipped_cached"] += 1
                    # cached pages don't give us the next cursor; stop this query
                    break
                params = dict(q.params)
                if cursor:
                    params["cursor"] = cursor
                data = client.search_people(params)
                store.put_raw("needle.people_search", req, data)
                store.commit()
                stats["calls"] += 1
                hits = data.get("hits") or []
                stats["hits"] += len(hits)
                log(f"[needle] {q.label} p{page}: {len(hits)} hits (budget day={client.budget.day})")
                cursor = data.get("cursor")
                if not cursor or len(hits) < 10:
                    break
    except BudgetExhausted as e:
        stats["stopped"] = str(e)
        log(f"[needle] stopped: {e}")
    return stats


def import_mcp_response(store: Store, kind: str, label: str, params: dict, payload: dict, page: int = 0) -> str:
    """Store a response obtained through the Needle MCP server in the same raw format."""
    collector = {"people": "needle.people_search", "jobs": "needle.jobs_search", "job": "needle.job",
                 "profile": "needle.profile", "company": "needle.company"}[kind]
    return store.put_raw(collector, {"label": label, "page": page, "params": params}, payload)


def iter_hits(store: Store) -> Iterator[dict[str, Any]]:
    import json
    for raw in store.raw_documents("needle.people_search"):
        for h in json.loads(raw["payload"]).get("hits", []):
            yield h
