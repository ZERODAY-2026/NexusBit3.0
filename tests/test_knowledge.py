import json

from lexlocal import config, knowledge


def _reload(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "KNOWLEDGE_DIR", tmp_path)
    knowledge.load.cache_clear()


def test_missing_files_fall_back(monkeypatch, tmp_path):
    _reload(monkeypatch, tmp_path)
    assert "rent" in knowledge.checklist("rental")
    assert knowledge.load("vague_terms.json")
    assert knowledge.disclaimer("en")["silent"]
    knowledge.load.cache_clear()


def test_placeholder_and_list_shapes(monkeypatch, tmp_path):
    (tmp_path / "vague_terms.json").write_text(json.dumps({"_placeholder": True, "items": ["foo bar"]}))
    (tmp_path / "one_sided_patterns.json").write_text(json.dumps(["baz"]))
    (tmp_path / "checklists.json").write_text(json.dumps({"_placeholder": True, "lease": ["rent"], "employment": ["salary"]}))
    _reload(monkeypatch, tmp_path)
    assert knowledge.load("vague_terms.json") == ["foo bar"]
    assert knowledge.load("one_sided_patterns.json") == ["baz"]
    assert knowledge.checklist("rental") == ["rent"]  # 'lease' key accepted for rental
    assert "_placeholder" not in knowledge.load("checklists.json")
    knowledge.load.cache_clear()


def test_malformed_file_tolerated(monkeypatch, tmp_path):
    (tmp_path / "glossary.json").write_text("{not json")
    (tmp_path / "disclaimers.json").write_text(json.dumps({"hi": {"disclaimer": "x"}}))
    _reload(monkeypatch, tmp_path)
    assert knowledge.load("glossary.json") == {}
    d = knowledge.disclaimer("hi")
    assert d["disclaimer"] == "x" and d["escalation"]  # missing keys filled from English defaults
    knowledge.load.cache_clear()
