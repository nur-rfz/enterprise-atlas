import json
from pathlib import Path

from atlas.builders import build_all
from atlas.collectors.needle import import_mcp_response
from atlas.collectors.web import import_web_record
from atlas.problems import WARRANTY_AFTERSALES_ANALYTICS as P
from atlas.report import buying_committee, org_tree
from atlas.store import Store

HITS = {"hits": [
    {"publicIdentifier": "a-b", "profileUrl": "https://www.linkedin.com/in/a-b", "fullName": "Anna Beispiel",
     "headline": "Head of Warranty Analytics bei Mercedes-Benz AG", "degree": "second"},
    {"publicIdentifier": None, "profileUrl": "https://www.linkedin.com/in/ACoXYZ", "fullName": "LinkedIn Member",
     "headline": "Category Manager IT Procurement Software at Mercedes-Benz AG", "degree": "out_of_network"},
    {"publicIdentifier": "c-d", "profileUrl": "https://www.linkedin.com/in/c-d", "fullName": "Carl Dee",
     "headline": "Data Lead at Some Other GmbH", "degree": "second"},
]}


def make():
    s = Store()
    import_mcp_response(s, "people", "t", {"companies": ["5383634"]}, HITS)
    import_web_record(s, {"url": "https://example-conf.org/session/warranty", "title": "Talk", "basis": "event_program",
                          "extracted": {"basis": "event_program", "entities": [
                              {"key": "p", "type": "Person", "name": "Anna Beispiel"},
                              {"key": "t", "type": "Topic", "name": "Predictive warranty analytics", "description": "warranty claims early warning"}],
                              "relations": [{"source_key": "p", "target_key": "t", "type": "SPOKE_ABOUT", "confidence": 0.9, "quote": "Anna Beispiel presents predictive warranty analytics."},
                                            {"source_key": "p", "target_key": "t", "type": "OWNS_PROJECT", "confidence": 0.9, "quote": "Anna owns it."}]}})
    build_all(s, P)
    return s


def test_end_to_end_roles_and_resolution():
    s = make()
    c = buying_committee(s, P)
    assert c["business_sponsor"]["top"][0]["label"] == "Anna Beispiel"
    assert any(p["title"].startswith("Category Manager IT Procurement") for p in c["procurement"]["top"])
    # web talk resolved onto the LinkedIn person, not a duplicate
    assert len(s.find_by_alias("Anna Beispiel")) == 1
    assert any(r["role"] == "champion" for r in s.entity("person:li:a-b")["props"]["buying_roles"])
    # a talk cannot establish project ownership
    [own] = [e for e in s.edges("type='OWNS_PROJECT'")]
    assert own.status == "uncertain" and own.confidence <= 0.45
    # alumni are not placed inside Mercedes
    assert s.entity("person:li:c-d")["props"].get("alumni")


def test_curation_survives_rebuild():
    s = make()
    a = [x for x in s.assertions("type='WORKS_ON'")][0]
    s.reject_assertion(a["id"], "wrong")
    s.upsert_entity("person:name:anna-b", __import__("atlas.ontology", fromlist=["NodeType"]).NodeType.PERSON, "Anna B.")
    s.merge_entities("person:name:anna-b", "person:li:a-b")
    build_all(s, P)
    assert not s.assertions("id=?", (a["id"],))
    assert s.entity("person:name:anna-b") is None


def test_org_tree_single_parent():
    t = org_tree(make(), "org:mercedes-benz-group")
    ids = []
    def walk(n):
        ids.append(n["id"]); [walk(c) for c in n["children"]]
    walk(t)
    assert len(ids) == len(set(ids))
