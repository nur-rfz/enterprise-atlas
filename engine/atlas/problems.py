"""Problem definitions: what the startup sells, expressed as the enterprise problem it solves.

The buying-center graph is always built *relative to a problem*. The same person can be
a problem owner for warranty analytics and irrelevant for a procurement-automation tool.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .titles import FUNCTIONS


@dataclass(frozen=True)
class Problem:
    id: str
    label: str
    description: str
    topics: dict[str, list[str]]                 # topic id -> patterns on normalized text
    owner_functions: frozenset[str]              # functions that operate the painful process
    owner_subfunctions: frozenset[str]           # most specific teams for the problem
    adjacent_functions: frozenset[str] = frozenset()
    technologies: tuple[str, ...] = ()
    search_titles: tuple[str, ...] = ()          # LinkedIn title keywords for harvesting
    job_keywords: tuple[str, ...] = ()
    web_queries: tuple[str, ...] = ()
    procurement_terms: tuple[str, ...] = ()      # TED / tender full-text terms
    cpv_codes: tuple[str, ...] = field(default=())

    @property
    def topic_id(self) -> str:
        return f"topic:{self.id}"


WARRANTY_AFTERSALES_ANALYTICS = Problem(
    id="warranty-aftersales-analytics",
    label="Warranty & after-sales analytics",
    description="Natural-language AI analytics for warranty, field-quality and after-sales data.",
    topics={
        "warranty": FUNCTIONS["warranty"][1],
        "after_sales": FUNCTIONS["after_sales"][1],
        "field_quality": [r"field (quality|data)", r"felddaten", r"reliability", r"zuverlaessigkeit", r"quality analytics", r"defect", r"root cause"],
        "analytics": [r"analytics?", r"data", r"daten", r"ai", r"ki", r"machine learning", r"business intelligence", r"bi", r"genai", r"llm"],
    },
    owner_functions=frozenset({"after_sales", "warranty", "quality"}),
    owner_subfunctions=frozenset({"warranty", "after_sales_data", "field_quality", "technical_after_sales", "digital_after_sales"}),
    adjacent_functions=frozenset({"data_ai", "it", "procurement", "finance"}),
    technologies=("Databricks", "SAP", "Qlik", "Power BI", "Tableau", "Snowflake", "Azure", "Palantir"),
    search_titles=(
        "warranty", "goodwill", "after-sales", "aftersales", "Gewährleistung", "Kulanz", "Kundendienst",
        "field quality", "Felddaten", "quality analytics", "after-sales data", "after-sales analytics",
        "service & parts", "technical after-sales", "IT procurement", "procurement IT services",
        "enterprise architect", "data product owner", "head of data",
    ),
    job_keywords=("warranty analytics", "after-sales data", "aftersales analytics", "field quality data",
                  "Gewährleistung Daten", "quality analytics", "after-sales AI"),
    web_queries=(
        "Mercedes-Benz after-sales data analytics conference speaker",
        "Mercedes-Benz warranty analytics project",
        "Mercedes-Benz field quality data AI",
        "Mercedes-Benz Databricks after-sales",
        "Mercedes-Benz case study warranty analytics implementation partner",
        "Mercedes-Benz Catena-X quality working group",
    ),
    procurement_terms=("Mercedes-Benz", "Daimler AG", "warranty analytics", "after-sales analytics"),
)

PROBLEMS = {p.id: p for p in [WARRANTY_AFTERSALES_ANALYTICS]}
