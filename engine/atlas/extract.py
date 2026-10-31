"""LLM extraction: page text -> typed ontology claims, each backed by a verbatim quote.

The model is asked for *observations*, not conclusions. The store then applies the basis
ceiling, so even if the model says "X owns the budget" from a conference page, that claim
is capped and marked uncertain.

Results are cached as raw documents (collector="llm.extraction") keyed on the page, so
rebuilding the graph never re-calls the API.
"""
from __future__ import annotations

import os
from typing import Literal, Optional

from pydantic import BaseModel, Field

from .ontology import Basis, EdgeType, NodeType

MODEL = os.environ.get("ATLAS_EXTRACT_MODEL", "claude-opus-5-5")

NodeTypeLit = Literal["Company", "BusinessUnit", "Function", "Team", "Person", "Role", "Project",
                      "Technology", "Partner", "Event", "Tender", "Topic"]
EdgeTypeLit = Literal[tuple(e.value for e in EdgeType)]  # type: ignore[valid-type]
BasisLit = Literal[tuple(b.value for b in Basis if b not in (Basis.HEURISTIC, Basis.ANALYST))]  # type: ignore[valid-type]


class XEntity(BaseModel):
    key: str = Field(description="Short unique key used by relations in this extraction, e.g. 'p1'.")
    id: Optional[str] = Field(default=None, description="Leave empty. Set only by analysts to pin an existing entity.")
    type: NodeTypeLit
    name: str
    title: Optional[str] = Field(default=None, description="Job title exactly as written, for persons.")
    affiliation: Optional[str] = Field(default=None, description="Organization the page ties this entity to.")
    description: Optional[str] = None


class XRelation(BaseModel):
    source_key: str
    target_key: str
    type: EdgeTypeLit
    confidence: float = Field(ge=0, le=1)
    quote: str = Field(description="Verbatim sentence from the page that supports this relation.")


class Extraction(BaseModel):
    basis: BasisLit = Field(description="What kind of source this page is.")
    published_date: Optional[str] = Field(default=None, description="ISO date if the page states one.")
    entities: list[XEntity]
    relations: list[XRelation]


SYSTEM = """You extract an evidence graph about how a large enterprise is organized and how it buys technology.

Rules:
- Only record what the page states. Every relation needs a verbatim supporting quote from the page.
- A talk, panel or article shows topic involvement (SPOKE_AT, SPOKE_ABOUT, CONTRIBUTED_TO). It does not show budget
  ownership, sponsorship or purchasing authority; never emit OWNS_PROJECT, SPONSORS or CONTROLS_PROCUREMENT from it.
- Vendor case studies are vendor claims: use CONTRIBUTED_TO, USES_TECH, PARTNERS_WITH.
- Procurement notices may support PROCURED, AWARDED_TO, CONTROLS_PROCUREMENT (for the named contracting contact).
- Job ads support HIRING_FOR (team -> topic) and USES_TECH.
- Use WORKS_IN for a person's stated organizational unit and HOLDS_ROLE only together with a Role entity.
- Keep person names exactly as written. Do not guess names, emails or titles.
- Confidence reflects how explicit the page is, not how important the fact is."""


def extract_page(text: str, url: str, title: str, focus: str) -> Extraction | None:
    """Call Claude with structured output. Returns None if the request is declined."""
    import anthropic

    client = anthropic.Anthropic()
    response = client.messages.parse(
        model=MODEL,
        max_tokens=16000,
        system=SYSTEM,
        output_config={"effort": "low"},
        messages=[{
            "role": "user",
            "content": f"Focus: {focus}\nURL: {url}\nTitle: {title}\n\n<page>\n{text}\n</page>",
        }],
        output_format=Extraction,
    )
    if response.stop_reason == "refusal":
        return None
    return response.parsed_output


def available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def node_type(t: str) -> NodeType:
    return NodeType(t)
