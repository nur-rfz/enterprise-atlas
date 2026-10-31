"""Mercedes-Benz target profile.

Seed structure is limited to what an official or primary source states. Each seed edge
cites its source. Everything below the business-unit level is discovered by collectors.
"""
from __future__ import annotations

OBSERVED = "2026-10-31"

COMPANY_ID = "org:mercedes-benz-group"

# LinkedIn company ids used to scope people / job searches (resolved through Needle).
LINKEDIN_COMPANIES = {
    "mercedes-benz_ag": "5383634",  # "Mercedes-Benz AG", 49,480 employees on LinkedIn (observed 2026-10-31)
}

SOURCES = {
    "linkedin_company": {
        "url": "https://www.linkedin.com/company/mercedes-benz_ag/",
        "title": "Mercedes-Benz AG · LinkedIn company page (imprint section)",
        "basis": "official_company",
        "provider": "Needle/LinkedIn",
        "access": "licensed",
        "excerpt": ("Represented by the Board of Management: Ola Källenius, Chairman; Jörg Burzer, Mathias Geisen, "
                    "Olaf Schick, Michael Schiebe, Britta Seeger, Oliver Thöne, Harald Wilhelm. Chairman of the "
                    "Supervisory Board: Martin Brudermüller. 49,480 employees on LinkedIn; HQ Stuttgart."),
    },
    "at_a_glance": {
        "url": "https://group.mercedes-benz.com/company/at-a-glance.html",
        "title": "Mercedes-Benz Group at a glance",
        "basis": "official_company",
        "provider": "web",
        "excerpt": ("Mercedes-Benz Group AG acts as holding company with governance, strategy and group-wide "
                    "services for the independent subsidiaries Mercedes-Benz AG and Mercedes-Benz Mobility AG."),
    },
    "annual_report_2025": {
        "url": "https://group.mercedes-benz.com/investors/reports-news/annual-reports/2025/",
        "title": "Mercedes-Benz Group Annual Report 2025",
        "basis": "official_company",
        "provider": "web",
        "excerpt": ("2025: customer-facing activities consolidated; Mercedes-Benz Mobility AG merged into "
                    "Mercedes-Benz AG. Mobility adjusted EBIT EUR 1,267m (2024: EUR 1,134m)."),
    },
    "mbition": {
        "url": "https://group.mercedes-benz.com/technologie/innovation/zusammenarbeit/mbition.html",
        "title": "MBition | Mercedes-Benz Group",
        "basis": "official_company",
        "provider": "web",
        "excerpt": "Im Jahr 2017 gründete die Mercedes-Benz AG ihre 100%-Tochtergesellschaft MBition GmbH.",
    },
    "mbti": {
        "url": "https://www.mercedes-benz-techinnovation.com/en/about-us",
        "title": "Mercedes-Benz Tech Innovation · About us",
        "basis": "official_company",
        "provider": "web",
        "excerpt": "100% part of Mercedes-Benz since foundation in 1998; describes itself as the largest tech company within Mercedes-Benz Group AG.",
    },
}

# id, type, label, aliases
UNITS = [
    ("org:mercedes-benz-group", "Company", "Mercedes-Benz Group", ["Mercedes-Benz Group AG", "Daimler AG", "Daimler", "Mercedes-Benz"]),
    ("bu:mb-ag", "BusinessUnit", "Mercedes-Benz AG", ["Mercedes Benz AG", "MBAG"]),
    ("bu:mb-cars", "BusinessUnit", "Mercedes-Benz Cars", ["MB Cars", "MBC", "PKW"]),
    ("bu:mb-vans", "BusinessUnit", "Mercedes-Benz Vans", ["MB Vans", "MBV", "Vans"]),
    ("bu:mb-mobility", "BusinessUnit", "Mercedes-Benz Mobility", ["Mercedes-Benz Mobility AG", "Mercedes-Benz Bank", "Daimler Financial Services"]),
    ("bu:mbition", "BusinessUnit", "MBition", ["MBition GmbH"]),
    ("bu:mbti", "BusinessUnit", "Mercedes-Benz Tech Innovation", ["MBTI", "Mercedes-Benz Tech Innovation GmbH", "Daimler TSS"]),
    ("bu:mb-amg", "BusinessUnit", "Mercedes-AMG", ["AMG", "Mercedes-AMG GmbH"]),
    ("bu:mb-os", "BusinessUnit", "MB.OS", ["MB.OS", "Mercedes-Benz Operating System"]),
    ("bu:mbrdi", "BusinessUnit", "Mercedes-Benz R&D India", ["MBRDI"]),
    ("bu:mbrdna", "BusinessUnit", "Mercedes-Benz R&D North America", ["MBRDNA"]),
    ("bu:mb-usa", "BusinessUnit", "Mercedes-Benz USA", ["MBUSA"]),
    ("bu:mb-sales-de", "BusinessUnit", "Mercedes-Benz Sales Germany", ["Mercedes-Benz Vertrieb Deutschland", "MBVD", "Mercedes-Benz Deutschland"]),
    # Separate listed company since the 2021 spin-off; profiles saying "Daimler AG ... Trucks" are historic.
    ("org:daimler-truck", "Company", "Daimler Truck", ["Daimler Truck AG", "Daimler Trucks", "Mercedes-Benz Trucks"]),
]

# child, parent, source key, confidence
STRUCTURE = [
    ("bu:mb-ag", "org:mercedes-benz-group", "at_a_glance", 0.95),
    ("bu:mb-mobility", "org:mercedes-benz-group", "at_a_glance", 0.8),
    ("bu:mb-mobility", "bu:mb-ag", "annual_report_2025", 0.85),
    ("bu:mbition", "bu:mb-ag", "mbition", 0.9),
    ("bu:mbti", "org:mercedes-benz-group", "mbti", 0.85),
]

# Parents for units that profiles mention but no official source above places yet.
# Stored as heuristic (inferred, capped) until an official source is added.
UNIT_PARENTS = {
    "bu:mb-cars": "bu:mb-ag", "bu:mb-vans": "bu:mb-ag", "bu:mb-os": "bu:mb-ag", "bu:mb-amg": "bu:mb-ag",
    "bu:mb-sales-de": "bu:mb-ag", "bu:mb-usa": "org:mercedes-benz-group", "bu:mbrdna": "org:mercedes-benz-group",
    "bu:mbrdi": "org:mercedes-benz-group",
}

BOARD = [
    ("Ola Källenius", "Chairman of the Board of Management"),
    ("Jörg Burzer", "Member of the Board of Management"),
    ("Mathias Geisen", "Member of the Board of Management"),
    ("Olaf Schick", "Member of the Board of Management"),
    ("Michael Schiebe", "Member of the Board of Management"),
    ("Britta Seeger", "Member of the Board of Management"),
    ("Oliver Thöne", "Member of the Board of Management"),
    ("Harald Wilhelm", "Member of the Board of Management"),
]

# Patterns matched against the normalize()d headline (umlauts folded, punctuation -> space).
UNIT_LEXICON: dict[str, list[str]] = {
    "bu:mb-cars": [r"(mb|mercedes benz) cars", r"pkw", r"passenger cars?", r"mbc"],
    "bu:mb-vans": [r"(mb |mercedes benz )?vans?", r"transporter"],
    "org:daimler-truck": [r"trucks?", r"daimler truck\w*", r"lkw", r"buses", r"bus", r"evobus", r"fuso", r"freightliner"],
    "bu:mb-mobility": [r"mobility", r"financial services", r"mercedes benz bank", r"leasing"],
    "bu:mb-amg": [r"amg"],
    "bu:mbition": [r"mbition"],
    "bu:mbti": [r"tech innovation", r"mbti", r"daimler tss"],
    "bu:mb-os": [r"mb os"],
    "bu:mbrdi": [r"mbrdi", r"r d india", r"research and development india"],
    "bu:mbrdna": [r"mbrdna", r"r d north america"],
    "bu:mb-usa": [r"mbusa", r"mercedes benz usa"],
    "bu:mb-sales-de": [r"vertrieb deutschland", r"mbvd", r"mercedes benz deutschland", r"mercedes benz germany"],
}

# Employer strings that count as "works for the target". Anything else in the employer slot
# (e.g. "IT-Projektmanager ... to Mercedes-Benz Germany") is treated as external / partner-side.
EMPLOYER_PATTERNS = [r"mercedes", r"mb", r"mb (cars|vans)", r"daimler ag", r"mbition", r"mbrdi", r"mbrdna", r"mbusa", r"amg"]
