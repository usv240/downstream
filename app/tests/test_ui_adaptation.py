from pathlib import Path


WEB = Path(__file__).resolve().parents[1] / "web"


def test_product_exposes_conflict_and_revision_loop_in_light_mode():
    html = (WEB / "downstream.html").read_text(encoding="utf-8")
    assert '<html lang="en" data-project="downstream">' in html
    assert "six owner facts" not in html.lower()
    assert "five owner facts and one retrieved-source conflict" in html
    assert 'id="revision-card"' in html
    assert "/static/downstream-v2.js" in html
    assert "/static/downstream-v2.css" in html


def test_frontend_makes_adaptation_and_evidence_visible():
    script = (WEB / "downstream-v2.js").read_text(encoding="utf-8")
    for evidence in (
        "Retrieved sources disagree",
        "answer_revisions",
        "source_conflicts_surfaced",
        "evidence_ledger",
        "/revise",
        "Revise and preserve history",
    ):
        assert evidence in script


def test_judge_page_states_measured_gates_and_has_no_mojibake():
    html = (WEB / "downstream-judges-v2.html").read_text(encoding="utf-8")
    for evidence in (
        "211",
        "26/26",
        "Versioned owner correction",
        "Section evidence ledger",
        "Conflict-driven question",
    ):
        assert evidence in html
    for broken in ("â€", "ðŸ", "ï¸"):
        assert broken not in html
