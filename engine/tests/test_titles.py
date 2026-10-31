from atlas.titles import parse_title
from atlas.targets.mercedes import UNIT_LEXICON
from atlas.problems import WARRANTY_AFTERSALES_ANALYTICS as P
from atlas.buying import infer_roles
from atlas.ontology import BuyingRole, Basis, EdgeType, clamp_confidence
from atlas.store import Store, normalize


def roles(h):
    return {r.role for r in infer_roles(parse_title(h, UNIT_LEXICON, P.topics), P)}


def test_director_in_domain_is_sponsor_hypothesis():
    tp = parse_title("Director of Service & Parts Business and Warranty & Goodwill Mercedes-Benz Cars bei Mercedes-Benz AG", UNIT_LEXICON)
    assert tp.seniority == "director"
    assert "warranty" in tp.subfunctions and "bu:mb-cars" in tp.unit_hints
    assert tp.employer_hint == "Mercedes-Benz AG"
    assert BuyingRole.BUSINESS_SPONSOR in roles(tp.raw)


def test_data_lead_in_aftersales_is_evaluator():
    r = roles("Team Lead Data, AI & Analytics After-Sales at Mercedes-Benz AG")
    assert BuyingRole.EVALUATOR in r and BuyingRole.PROBLEM_OWNER in r


def test_senior_outside_domain_is_not_sponsor():
    # seniority alone must not create a sponsor
    assert BuyingRole.BUSINESS_SPONSOR not in roles("Vice President Marketing at Mercedes-Benz AG")


def test_german_titles():
    tp = parse_title("Teamleiter Gewährleistung und Kulanz bei Mercedes-Benz AG", UNIT_LEXICON)
    assert tp.seniority == "manager" and "warranty" in tp.subfunctions
    assert parse_title("After-Sales Leiter bei Daimler AG").seniority == "director"
    assert parse_title("After-Sales Leiter bei Daimler AG").historic_employer


def test_pipe_segments_keep_employer():
    tp = parse_title("Service Associate | invoice & warranty bei Mercedes-Benz AG")
    assert tp.employer_hint == "Mercedes-Benz AG" and "warranty" in tp.subfunctions


def test_external_and_intern():
    assert BuyingRole.INTRODUCER in roles("IT-Projektmanager Retail DMS Consultant AfterSales + special warranty to Mercedes-Benz Germany")
    assert roles("Werkstudent After-Sales Data bei Mercedes-Benz AG") == set()


def test_trucks_flagged():
    assert "org:daimler-truck" in parse_title("Manager Technical After-Sales Trucks", UNIT_LEXICON).unit_hints


def test_basis_ceiling():
    c, s = clamp_confidence(EdgeType.OWNS_PROJECT, Basis.EVENT_PROGRAM, 0.95)
    assert s == "uncertain" and c <= 0.45  # a talk never proves ownership
    c, s = clamp_confidence(EdgeType.SPOKE_ABOUT, Basis.EVENT_PROGRAM, 0.95)
    assert s == "confirmed"


def test_store_requires_evidence_and_aggregates():
    st = Store()
    from atlas.ontology import NodeType
    st.upsert_entity("a", NodeType.PERSON, "A"); st.upsert_entity("b", NodeType.TEAM, "B")
    try:
        st.assert_edge("a", "b", EdgeType.WORKS_IN, basis=Basis.SELF_REPORTED_PROFILE, confidence=.7, evidence_id=None, extractor="t")
        assert False
    except ValueError:
        pass
    e1 = st.put_evidence(url="u1", title="t", basis=Basis.SELF_REPORTED_PROFILE, provider="p")
    e2 = st.put_evidence(url="u2", title="t", basis=Basis.OFFICIAL_COMPANY, provider="p")
    st.assert_edge("a", "b", EdgeType.WORKS_IN, basis=Basis.SELF_REPORTED_PROFILE, confidence=.7, evidence_id=e1, extractor="t")
    st.assert_edge("a", "b", EdgeType.WORKS_IN, basis=Basis.OFFICIAL_COMPANY, confidence=.9, evidence_id=e2, extractor="t")
    [edge] = st.edges()
    assert edge.status == "confirmed" and edge.confidence > .9 and len(edge.assertions) == 2


def test_normalize_umlauts():
    assert normalize("Jörg Qualität") == normalize("Joerg Qualitaet")
