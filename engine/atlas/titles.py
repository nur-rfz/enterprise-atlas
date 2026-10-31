"""Parse self-reported job titles / LinkedIn headlines (English + German).

A headline such as
    "Director of Service & Parts Business and Warranty & Goodwill Mercedes-Benz Cars bei Mercedes-Benz AG"
becomes
    seniority=director, functions=[after_sales], subfunctions=[warranty, parts], unit_hints=[mb-cars],
    employer_hint="Mercedes-Benz AG", external=False

Everything here is lexical. Output is used to *place* people in the organizational
graph and to form buying-role *hypotheses*; it never confirms authority.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .store import normalize

# --------------------------------------------------------------------------- functions
# function id -> (label, patterns). Patterns are matched on normalize()d text with word
# boundaries, so umlauts are folded: "Qualität" -> "qualitaet".
FUNCTIONS: dict[str, tuple[str, list[str]]] = {
    "after_sales": ("After-Sales", [
        r"after ?sales?", r"aftersales", r"kundendienst", r"service (and|&)? ?parts", r"service parts",
        r"parts business", r"teile(vertrieb|geschaeft)?", r"service operations", r"workshop", r"werkstatt",
        r"customer service", r"service business", r"service technik", r"service product",
    ]),
    "warranty": ("Warranty & Goodwill", [
        r"warranty", r"gewaehrleistung", r"garantie", r"goodwill", r"kulanz", r"claims?",
    ]),
    "quality": ("Quality & Reliability", [
        r"quality", r"qualitaet", r"qm", r"reliability", r"zuverlaessigkeit", r"field (data|quality)",
        r"felddaten", r"defect", r"fehler(analyse)?", r"root cause",
    ]),
    "data_ai": ("Data & AI", [
        r"data", r"daten", r"analytics?", r"analyst", r"ai", r"ki", r"kuenstliche intelligenz",
        r"machine learning", r"ml", r"data scien\w*", r"business intelligence", r"bi", r"genai",
        r"llm", r"data product", r"data engineer\w*",
    ]),
    "it": ("IT & Architecture", [
        r"it", r"cio", r"architect\w*", r"architektur", r"platform", r"plattform", r"cloud", r"security",
        r"cyber", r"infrastructure", r"sap", r"devops", r"software", r"informatik", r"integration",
        r"enterprise architecture", r"solution architect", r"applikation\w*", r"application",
    ]),
    "procurement": ("Procurement", [
        r"procurement", r"einkauf", r"einkaeufer\w*", r"purchas\w*", r"buyer", r"category manag\w*",
        r"sourcing", r"supplier", r"lieferant\w*", r"beschaffung", r"vendor management",
    ]),
    "sales_marketing": ("Sales & Marketing", [
        r"sales", r"vertrieb", r"marketing", r"crm", r"retail", r"dealer", r"haendler\w*",
        r"customer (experience|journey|targeting)", r"brand", r"key account",
    ]),
    "finance": ("Finance & Controlling", [r"controlling", r"controller", r"finance", r"finanz\w*", r"cost\w*", r"kosten"]),
    "rnd": ("R&D / Engineering", [r"development", r"entwicklung", r"engineer\w*", r"ingenieur\w*", r"r ?(and|&) ?d", r"research", r"forschung"]),
    "production": ("Production", [r"production", r"produktion", r"plant", r"manufactur\w*", r"fertigung", r"montage", r"logistics", r"logistik"]),
    "strategy": ("Strategy & Transformation", [r"strateg\w*", r"transformation", r"innovation", r"digital\w*", r"pmo", r"program"]),
    "hr": ("HR", [r"hr", r"human resources", r"personal\w*", r"recruit\w*", r"talent"]),
    "legal": ("Legal & Compliance", [r"legal", r"recht", r"compliance", r"counsel", r"jurist\w*"]),
}

# Specific sub-teams that sit under a function. (parent function, label, patterns)
SUBFUNCTIONS: dict[str, tuple[str, str, list[str]]] = {
    "warranty": ("after_sales", "Warranty & Goodwill", FUNCTIONS["warranty"][1]),
    "parts": ("after_sales", "Parts", [r"parts", r"teile", r"ersatzteil\w*"]),
    "technical_after_sales": ("after_sales", "Technical After-Sales", [r"technical after ?sales", r"technischer kundendienst", r"diagnos\w*", r"field service", r"service technik", r"after sales technik"]),
    "digital_after_sales": ("after_sales", "Digital After-Sales", [r"digital after ?sales", r"after ?sales digital\w*", r"connected service\w*"]),
    "after_sales_data": ("after_sales", "After-Sales Data, AI & Analytics", [r"(data|analytics|ai|ki)\b.*after ?sales", r"after ?sales\b.*(data|analytics|ai|ki)\b"]),
    "field_quality": ("quality", "Field Quality", [r"field (quality|data)", r"felddaten", r"feldqualitaet", r"market quality"]),
    "it_procurement": ("procurement", "IT & Services Procurement", [r"it (procurement|purchasing|einkauf)", r"(procurement|purchasing|einkauf) (it|services|software|digital)", r"indirect", r"non production", r"general purchasing", r"nonproduction"]),
    "enterprise_architecture": ("it", "Enterprise Architecture", [r"enterprise architect\w*", r"solution architect\w*", r"architecture"]),
}

SENIORITY: list[tuple[str, int, list[str]]] = [
    # (label, rank, patterns) - first match wins, so order from most to least specific
    ("intern", 0, [r"working student", r"werkstudent\w*", r"intern(ship)?", r"praktikant\w*", r"trainee", r"thesis", r"abschlussarbeit", r"doktorand\w*", r"phd candidate", r"apprentice", r"azubi", r"auszubildende\w*", r"dual\w* stud\w*"]),
    ("assistant", 1, [r"(executive |team |personal )?assistan\w*", r"assistenz\w*", r"sekretariat", r"office manag\w*"]),
    ("board", 6, [r"member of the board", r"board member", r"vorstand\w*", r"chief \w+ officer", r"ceo", r"cfo", r"cto", r"cio", r"chairman", r"vorsitzende\w*"]),
    ("vp", 5, [r"(senior |executive )?vice president", r"svp", r"evp", r"vp", r"bereichsleit\w*", r"generalbevollmaechtigt\w*"]),
    ("director", 4, [r"director", r"direktor\w*", r"head of", r"head", r"leiter\w*", r"leitung", r"abteilungsleit\w*", r"hauptabteilungsleit\w*", r"department lead\w*"]),
    ("manager", 3, [r"team ?lead\w*", r"teamleit\w*", r"group lead\w*", r"gruppenleit\w*", r"lead", r"senior manager", r"manager\w*", r"product owner", r"projektleit\w*", r"project lead\w*", r"projektmanager\w*", r"project manager\w*"]),
    ("ic", 2, [r"specialist", r"spezialist\w*", r"engineer\w*", r"analyst", r"consultant", r"berater\w*", r"referent\w*", r"sachbearbeit\w*", r"associate", r"expert\w*", r"experte", r"developer", r"entwickler\w*", r"architect\w*", r"scientist", r"assessor", r"coordinator", r"koordinator\w*", r"planer\w*", r"planning", r"operations"]),
]

EXTERNAL_PATTERNS = [
    r"\bfor mercedes", r"\bto mercedes", r"@ ?customer", r"\bexternal\b", r"\bextern\b", r"freelanc\w*",
    r"contractor", r"consultant (at|bei) (?!mercedes)", r"dienstleister", r"\bon behalf of\b",
]

EMPLOYER_SPLIT = re.compile(r"\s(?:at|bei|@|chez)\s", re.IGNORECASE)


@dataclass
class TitleParse:
    raw: str
    title: str
    employer_hint: str | None
    seniority: str
    seniority_rank: int
    functions: list[str] = field(default_factory=list)
    subfunctions: list[str] = field(default_factory=list)
    unit_hints: list[str] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)
    external: bool = False
    historic_employer: bool = False

    @property
    def primary_function(self) -> str | None:
        # The most specific domain wins over generic ones such as data_ai or strategy.
        order = ["warranty", "procurement", "quality", "after_sales", "it", "data_ai", "finance",
                 "sales_marketing", "rnd", "production", "hr", "legal", "strategy"]
        for f in order:
            if f in self.functions:
                return "after_sales" if f == "warranty" else f
        return None


def _match_any(patterns: list[str], text: str) -> bool:
    return any(re.search(rf"\b(?:{p})\b", text) for p in patterns)


def split_headline(headline: str) -> tuple[str, str | None]:
    """'Warranty Guidelines bei Mercedes-Benz AG | Psychology' -> ('Warranty Guidelines | Psychology', 'Mercedes-Benz AG')."""
    segments = [s.strip() for s in headline.split("|")]
    for i, seg in enumerate(segments):
        parts = EMPLOYER_SPLIT.split(seg, maxsplit=1)
        if len(parts) == 2:
            employer = parts[1].strip(" -–·,") or None
            segments[i] = parts[0]
            title = " | ".join(s for s in segments if s).strip(" -–·,|")
            return title, employer
    return headline.strip(" -–·,|"), None


def parse_title(headline: str, unit_lexicon: dict[str, list[str]] | None = None,
                topic_lexicon: dict[str, list[str]] | None = None) -> TitleParse:
    raw = (headline or "").strip()
    title, employer = split_headline(raw)
    norm = normalize(raw)
    title_norm = normalize(title)

    seniority, rank = "unknown", 1
    for label, r, pats in SENIORITY:
        if _match_any(pats, title_norm):
            seniority, rank = label, r
            break

    functions = [fid for fid, (_, pats) in FUNCTIONS.items() if _match_any(pats, title_norm)]
    subfunctions = [sid for sid, (_, _, pats) in SUBFUNCTIONS.items() if _match_any(pats, title_norm)]
    for sid in subfunctions:
        parent = SUBFUNCTIONS[sid][0]
        if parent not in functions:
            functions.append(parent)

    units = []
    for uid, pats in (unit_lexicon or {}).items():
        if _match_any(pats, norm):
            units.append(uid)
    topics = [tid for tid, pats in (topic_lexicon or {}).items() if _match_any(pats, norm)]

    external = _match_any(EXTERNAL_PATTERNS, norm) and not (employer and "mercedes" in normalize(employer))
    historic = bool(employer and re.search(r"\bdaimler ag\b", normalize(employer)))

    return TitleParse(raw=raw, title=title, employer_hint=employer, seniority=seniority, seniority_rank=rank,
                      functions=functions, subfunctions=subfunctions, unit_hints=units, topics=topics,
                      external=external, historic_employer=historic)
