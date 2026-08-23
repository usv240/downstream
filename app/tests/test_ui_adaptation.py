import sys
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
        "Versioned owner correction",
        "Section evidence ledger",
        "Conflict-driven question",
    ):
        assert evidence in html
    for broken in ("â€", "ðŸ", "ï¸"):
        assert broken not in html


def test_the_judge_page_test_count_matches_the_suite_it_describes():
    """A hardcoded number here went stale silently once. Count the suite instead.

    The page tells a judge how many tests exist. If that figure and the suite ever disagree, the
    page is overstating or understating measured work, and this is the check that notices.
    """
    import re
    import subprocess

    html = (WEB / "downstream-judges-v2.html").read_text(encoding="utf-8")
    claimed = re.search(r"<b>(\d{2,5})</b><span>standalone automated tests", html)
    assert claimed, "the judge page no longer states a test count"

    collected = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"],
        cwd=WEB.parent,
        capture_output=True,
        text=True,
    )
    actual = re.search(r"(\d+) tests? collected", collected.stdout)
    assert actual, f"could not read the collected count: {collected.stdout[-500:]}"
    assert int(claimed.group(1)) == int(actual.group(1)), (
        f"the judge page claims {claimed.group(1)} tests but the suite has {actual.group(1)}"
    )


def test_the_judge_page_leads_with_autonomy_not_a_manual_tour():
    """The product became autonomous; the page a judge lands on has to say so."""
    html = (WEB / "downstream-judges-v2.html").read_text(encoding="utf-8").lower()
    for token in ("autonom", "one request", "durable wake", "cloud scheduler", "continue clicks"):
        assert token in html, token


def test_the_landing_page_leads_with_autonomy():
    html = (WEB / "downstream.html").read_text(encoding="utf-8").lower()
    hero = html[: html.index("</section>")]
    assert "on its own" in hero or "autonom" in hero, "the hero still describes a question loop"
    for token in ("durable wake", "cloud scheduler", "autonomy receipt"):
        assert token in html, token


def test_the_evidence_dashboard_executes_a_real_run():
    html = (WEB / "downstream-evidence.html").read_text(encoding="utf-8")
    js = (WEB / "downstream-evidence.js").read_text(encoding="utf-8")
    assert 'id="autonomy-tiles"' in html
    assert 'id="autonomy-timeline"' in html
    assert "/downstream/demo/run" in js, "the dashboard should run the agent, not read a fixture"
