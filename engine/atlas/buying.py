"""Buying-center inference.

Turns an organizational placement (function, sub-team, seniority) plus activity evidence
(talks, job ads, tenders) into *hypotheses* about buying roles for one problem.

Rules of the road:
* Seniority alone never makes someone a sponsor; they must sit in a problem-owning function.
* Every hypothesis is stored with basis=heuristic, so it is capped and marked "inferred".
* The rationale string says exactly which signals were used.
"""
from __future__ import annotations

from dataclasses import dataclass

from .ontology import BuyingRole, EdgeType
from .problems import Problem
from .titles import TitleParse, _match_any
from .store import normalize

ROLE_EDGE = {
    BuyingRole.PROBLEM_OWNER: EdgeType.OWNS_PROBLEM,
    BuyingRole.BUSINESS_SPONSOR: EdgeType.SPONSORS,
    BuyingRole.EVALUATOR: EdgeType.EVALUATES,
    BuyingRole.TECHNICAL_APPROVER: EdgeType.APPROVES_INTEGRATION,
    BuyingRole.PROCUREMENT: EdgeType.CONTROLS_PROCUREMENT,
    BuyingRole.CHAMPION: EdgeType.INFLUENCES,
    BuyingRole.INTRODUCER: EdgeType.INTRODUCES_TO,
    BuyingRole.USER: EdgeType.WORKS_ON,
}

ROLE_WEIGHT = {
    BuyingRole.BUSINESS_SPONSOR: 1.0,
    BuyingRole.PROBLEM_OWNER: 0.95,
    BuyingRole.EVALUATOR: 0.9,
    BuyingRole.CHAMPION: 0.8,
    BuyingRole.TECHNICAL_APPROVER: 0.6,
    BuyingRole.PROCUREMENT: 0.5,
    BuyingRole.INTRODUCER: 0.55,
    BuyingRole.USER: 0.35,
}

STRONG_IT = [r"it", r"architect\w*", r"architektur", r"platform", r"plattform", r"cloud", r"integration", r"sap",
             r"devops", r"infrastructure", r"cio", r"informatik", r"security"]

REACHABILITY = {"first": 1.0, "second": 0.8, "third_plus": 0.45, "out_of_network": 0.3, None: 0.3}


@dataclass
class RoleHypothesis:
    role: BuyingRole
    confidence: float
    rationale: str


def topic_hits(problem: Problem, text: str) -> list[str]:
    n = normalize(text)
    return [t for t, pats in problem.topics.items() if _match_any(pats, n)]


def infer_roles(tp: TitleParse, problem: Problem) -> list[RoleHypothesis]:
    if tp.seniority == "intern":
        return []
    if tp.seniority == "assistant":
        domain = set(tp.functions) & problem.owner_functions
        return [RoleHypothesis(BuyingRole.INTRODUCER, 0.35,
                               "Assistant to leadership in the problem domain; controls calendars and internal routing.")] if domain else []
    fn = set(tp.functions)
    sub = set(tp.subfunctions)
    domain = fn & problem.owner_functions
    domain_sub = sub & problem.owner_subfunctions
    hits = topic_hits(problem, tp.raw)
    rank = tp.seniority_rank
    out: list[RoleHypothesis] = []
    where = ", ".join(sorted(domain_sub or domain)) or "-"

    if tp.external:
        out.append(RoleHypothesis(BuyingRole.INTRODUCER, 0.45,
                                  "Works for a partner/contractor on the target's account; possible warm introduction route."))
        if domain:
            out.append(RoleHypothesis(BuyingRole.CHAMPION, 0.3,
                                      f"External delivery role inside the problem domain ({where})."))
        return out

    if domain and "procurement" not in fn:
        if rank >= 4:
            out.append(RoleHypothesis(BuyingRole.BUSINESS_SPONSOR, 0.5 + 0.05 * bool(domain_sub),
                                      f"Director-level or above in a problem-owning function ({where}). Budget ownership is not verified."))
            out.append(RoleHypothesis(BuyingRole.PROBLEM_OWNER, 0.45,
                                      f"Leads the function that operates the process ({where})."))
        elif rank == 3:
            data_role = "data_ai" in fn and not (fn & {"warranty", "quality"}) and "after_sales_data" in sub
            out.append(RoleHypothesis(BuyingRole.PROBLEM_OWNER, 0.4 if data_role else 0.5 + 0.08 * bool(domain_sub),
                                      f"Manager / team lead inside the problem domain ({where})."))
        else:
            out.append(RoleHypothesis(BuyingRole.USER, 0.5,
                                      f"Individual contributor in the problem domain ({where}); likely daily user of the data."))

    if "data_ai" in fn:
        if domain:
            out.append(RoleHypothesis(BuyingRole.EVALUATOR, 0.58 if rank >= 3 else 0.45,
                                      f"Data/analytics role embedded in the problem domain ({where}); would assess an analytics tool."))
        elif rank >= 3 and hits:
            out.append(RoleHypothesis(BuyingRole.EVALUATOR, 0.3,
                                      "Data/AI lead without a stated link to the problem domain."))

    title_n = normalize(tp.title)
    strong_it = _match_any(STRONG_IT, title_n)
    architect = _match_any([r"architect\w*", r"architektur"], title_n)
    if "it" in fn and strong_it and "procurement" not in fn and (rank >= 3 or architect):
        boost = 0.15 if (domain or "enterprise_architecture" in sub) else 0.0
        out.append(RoleHypothesis(BuyingRole.TECHNICAL_APPROVER, 0.3 + boost,
                                  "IT / architecture role" + (" serving the problem domain" if domain else "") +
                                  "; integration sign-off is plausible, not verified."))

    if "procurement" in fn:
        boost = 0.15 if ("it_procurement" in sub or domain) else 0.0
        out.append(RoleHypothesis(BuyingRole.PROCUREMENT, 0.35 + boost,
                                  "Procurement role" + (" for IT/indirect services" if boost else "") +
                                  "; controls the vendor process, not the business need."))
    return out


def score_person(roles: list[RoleHypothesis], tp: TitleParse, problem: Problem, degree: str | None,
                 name_visible: bool, evidence_count: int, activity_bonus: float = 0.0) -> dict:
    """0-100 composite for ranking. Every component is returned so the UI can explain it."""
    if not roles:
        return {"score": 0, "problem_fit": 0, "role_strength": 0, "evidence": 0, "reachability": 0}
    hits = topic_hits(problem, tp.raw)
    fit = min(1.0, 0.25 * len(hits) + 0.35 * bool(set(tp.subfunctions) & problem.owner_subfunctions)
              + 0.2 * bool(set(tp.functions) & problem.owner_functions))
    role_strength = max(ROLE_WEIGHT[r.role] * r.confidence / 0.6 for r in roles)
    role_strength = min(1.0, role_strength)
    evidence = min(1.0, 0.35 + 0.2 * (evidence_count - 1) + activity_bonus)
    reach = REACHABILITY.get(degree, 0.3) * (1.0 if name_visible else 0.7)
    score = 100 * (0.4 * fit + 0.3 * role_strength + 0.15 * evidence + 0.15 * reach)
    return {
        "score": round(score), "problem_fit": round(fit * 100), "role_strength": round(role_strength * 100),
        "evidence": round(evidence * 100), "reachability": round(reach * 100),
    }
