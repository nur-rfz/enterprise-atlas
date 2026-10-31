# data/

Raw collector output and the SQLite store live here and are git-ignored, because they
contain named individuals (LinkedIn search results, conference speaker pages).

* `needle/*.jsonl` – Needle LinkedIn responses (`{"kind": "people", "label", "params", "payload"}` per line)
* `web/*.jsonl` – web records, optionally with a pre-attached extraction
* `atlas.sqlite` – the ontology store, rebuilt from the raw files with `python -m atlas.cli import ...`
