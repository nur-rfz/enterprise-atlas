"""Enterprise Atlas ontology.

Two overlapping graphs share one store:

* the organizational graph  (Company -> BusinessUnit -> Function -> Team <- Person)
* the buying-center graph   (who owns a problem, sponsors, evaluates, approves, procures, introduces)

Every edge is an aggregation of one or more *assertions*. An assertion is a single
claim made by a single piece of evidence: it always carries a source, an observation
date, a confidence and a *basis* (what kind of observation supports it).

The basis matters because a source type can only establish certain relationships.
A conference talk establishes topic involvement (SPOKE_ABOUT); it never establishes
budget ownership. ``MAX_CONFIDENCE_BY_BASIS`` enforces that ceiling at write time.
"""
from __future__ import annotations

from enum import Enum


class NodeType(str, Enum):
    COMPANY = "Company"
    BUSINESS_UNIT = "BusinessUnit"
    FUNCTION = "Function"
    TEAM = "Team"
    PERSON = "Person"
    ROLE = "Role"
    PROJECT = "Project"
    TECHNOLOGY = "Technology"
    PARTNER = "Partner"
    EVENT = "Event"
    TENDER = "Tender"
    TOPIC = "Topic"


class EdgeType(str, Enum):
    # organizational graph
    BELONGS_TO = "BELONGS_TO"            # unit/function/team -> parent
    WORKS_IN = "WORKS_IN"                # person -> team/function/unit/company
    HOLDS_ROLE = "HOLDS_ROLE"            # person -> role
    REPORTS_TO = "REPORTS_TO"            # person -> person
    # buying-center graph
    OWNS_PROBLEM = "OWNS_PROBLEM"        # person/function -> topic
    OWNS_PROJECT = "OWNS_PROJECT"        # person/function -> project
    SPONSORS = "SPONSORS"                # person -> project
    EVALUATES = "EVALUATES"              # person/function -> technology/project
    APPROVES_INTEGRATION = "APPROVES_INTEGRATION"
    CONTROLS_PROCUREMENT = "CONTROLS_PROCUREMENT"
    INFLUENCES = "INFLUENCES"
    INTRODUCES_TO = "INTRODUCES_TO"
    # activity / ecosystem
    SPOKE_ABOUT = "SPOKE_ABOUT"          # person -> topic/project (event evidence)
    SPOKE_AT = "SPOKE_AT"                # person -> event
    CONTRIBUTED_TO = "CONTRIBUTED_TO"    # person/partner -> project
    WORKS_ON = "WORKS_ON"                # person/team -> topic (from title/job ad)
    HIRING_FOR = "HIRING_FOR"            # team/function -> topic (job ad)
    USES_TECH = "USES_TECH"
    PARTNERS_WITH = "PARTNERS_WITH"
    PROCURED = "PROCURED"                # company/unit -> tender
    AWARDED_TO = "AWARDED_TO"            # tender -> partner
    MEMBER_OF = "MEMBER_OF"              # company/person -> association / working group


class Layer(str, Enum):
    ORGANIZATION = "organization"
    BUYING_CENTER = "buying_center"
    ECOSYSTEM = "ecosystem"


class Basis(str, Enum):
    """What kind of observation supports an assertion."""

    SELF_REPORTED_PROFILE = "self_reported_profile"  # LinkedIn headline / profile
    OFFICIAL_COMPANY = "official_company"            # company website, annual report, imprint
    PROCUREMENT_RECORD = "procurement_record"        # TED / national tender notice or award
    EVENT_PROGRAM = "event_program"                  # agenda, speaker bio, slides
    VENDOR_CLAIM = "vendor_claim"                    # vendor / SI case study
    JOB_AD = "job_ad"                                # vacancy text
    ASSOCIATION = "association"                      # working group / committee listing
    PUBLICATION = "publication"                      # paper, patent, OSS contribution
    PRESS = "press"                                  # 3rd-party press
    HEURISTIC = "heuristic"                          # derived by the engine from other assertions
    ANALYST = "analyst"                              # added manually by a human


# What each basis is allowed to establish, and the ceiling on confidence.
# Anything not listed for a basis is capped at the heuristic ceiling and marked inferred.
ESTABLISHES: dict[Basis, set[EdgeType]] = {
    Basis.SELF_REPORTED_PROFILE: {EdgeType.WORKS_IN, EdgeType.HOLDS_ROLE, EdgeType.WORKS_ON},
    Basis.OFFICIAL_COMPANY: {
        EdgeType.BELONGS_TO, EdgeType.WORKS_IN, EdgeType.HOLDS_ROLE, EdgeType.OWNS_PROJECT,
        EdgeType.CONTROLS_PROCUREMENT, EdgeType.USES_TECH, EdgeType.PARTNERS_WITH, EdgeType.REPORTS_TO,
    },
    Basis.PROCUREMENT_RECORD: {
        EdgeType.PROCURED, EdgeType.AWARDED_TO, EdgeType.CONTROLS_PROCUREMENT, EdgeType.OWNS_PROJECT,
        EdgeType.USES_TECH,
    },
    Basis.EVENT_PROGRAM: {EdgeType.SPOKE_AT, EdgeType.SPOKE_ABOUT, EdgeType.WORKS_IN, EdgeType.HOLDS_ROLE},
    Basis.VENDOR_CLAIM: {EdgeType.CONTRIBUTED_TO, EdgeType.USES_TECH, EdgeType.PARTNERS_WITH},
    Basis.JOB_AD: {EdgeType.HIRING_FOR, EdgeType.USES_TECH, EdgeType.BELONGS_TO},
    Basis.ASSOCIATION: {EdgeType.MEMBER_OF, EdgeType.CONTRIBUTED_TO},
    Basis.PUBLICATION: {EdgeType.CONTRIBUTED_TO, EdgeType.WORKS_ON, EdgeType.USES_TECH},
    Basis.PRESS: {EdgeType.PARTNERS_WITH, EdgeType.USES_TECH, EdgeType.OWNS_PROJECT, EdgeType.HOLDS_ROLE},
    Basis.HEURISTIC: set(),
    Basis.ANALYST: set(EdgeType),
}

MAX_CONFIDENCE_BY_BASIS: dict[Basis, float] = {
    Basis.SELF_REPORTED_PROFILE: 0.85,
    Basis.OFFICIAL_COMPANY: 0.95,
    Basis.PROCUREMENT_RECORD: 0.95,
    Basis.EVENT_PROGRAM: 0.9,
    Basis.VENDOR_CLAIM: 0.7,
    Basis.JOB_AD: 0.8,
    Basis.ASSOCIATION: 0.85,
    Basis.PUBLICATION: 0.85,
    Basis.PRESS: 0.75,
    Basis.HEURISTIC: 0.6,
    Basis.ANALYST: 1.0,
}

# A claim outside what its basis can establish is never "confirmed".
UNSUPPORTED_CEILING = 0.45

LAYER_OF: dict[EdgeType, Layer] = {
    EdgeType.BELONGS_TO: Layer.ORGANIZATION,
    EdgeType.WORKS_IN: Layer.ORGANIZATION,
    EdgeType.HOLDS_ROLE: Layer.ORGANIZATION,
    EdgeType.REPORTS_TO: Layer.ORGANIZATION,
    EdgeType.OWNS_PROBLEM: Layer.BUYING_CENTER,
    EdgeType.OWNS_PROJECT: Layer.BUYING_CENTER,
    EdgeType.SPONSORS: Layer.BUYING_CENTER,
    EdgeType.EVALUATES: Layer.BUYING_CENTER,
    EdgeType.APPROVES_INTEGRATION: Layer.BUYING_CENTER,
    EdgeType.CONTROLS_PROCUREMENT: Layer.BUYING_CENTER,
    EdgeType.INFLUENCES: Layer.BUYING_CENTER,
    EdgeType.INTRODUCES_TO: Layer.BUYING_CENTER,
    EdgeType.SPOKE_ABOUT: Layer.BUYING_CENTER,
    EdgeType.WORKS_ON: Layer.BUYING_CENTER,
    EdgeType.HIRING_FOR: Layer.BUYING_CENTER,
    EdgeType.SPOKE_AT: Layer.ECOSYSTEM,
    EdgeType.CONTRIBUTED_TO: Layer.ECOSYSTEM,
    EdgeType.USES_TECH: Layer.ECOSYSTEM,
    EdgeType.PARTNERS_WITH: Layer.ECOSYSTEM,
    EdgeType.PROCURED: Layer.ECOSYSTEM,
    EdgeType.AWARDED_TO: Layer.ECOSYSTEM,
    EdgeType.MEMBER_OF: Layer.ECOSYSTEM,
}


class BuyingRole(str, Enum):
    """Buying-center roles. Never derived from seniority alone."""

    PROBLEM_OWNER = "problem_owner"          # operates the process that has the pain
    BUSINESS_SPONSOR = "business_sponsor"    # owns the business outcome / budget line
    EVALUATOR = "evaluator"                  # data / analytics lead who assesses the tool
    TECHNICAL_APPROVER = "technical_approver"  # IT / architecture / security sign-off
    PROCUREMENT = "procurement"              # controls the vendor process
    CHAMPION = "champion"                    # publicly invested in the topic
    INTRODUCER = "introducer"                # partner / SI / association contact
    USER = "user"                            # end user of the capability


def clamp_confidence(edge_type: EdgeType, basis: Basis, confidence: float) -> tuple[float, str]:
    """Apply the basis ceiling. Returns (confidence, status)."""
    if basis == Basis.HEURISTIC:
        return min(confidence, MAX_CONFIDENCE_BY_BASIS[basis]), "inferred"
    if edge_type not in ESTABLISHES[basis]:
        return min(confidence, UNSUPPORTED_CEILING), "uncertain"
    c = min(confidence, MAX_CONFIDENCE_BY_BASIS[basis])
    return c, ("confirmed" if c >= 0.7 else "inferred")


def combine(confidences: list[float]) -> float:
    """Noisy-OR over independent assertions."""
    p = 1.0
    for c in confidences:
        p *= 1.0 - max(0.0, min(1.0, c))
    return round(1.0 - p, 4)
