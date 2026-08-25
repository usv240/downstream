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


def test_the_correction_example_targets_an_answer_the_run_has_not_already_revised():
    """A worked example that changes nothing on screen is worse than no example.

    It used to be pinned to access_heavy_rain, which the one-request demonstration corrects
    internally, so clicking it produced a third version with identical text and a draft that
    visibly did nothing.
    """
    js = (WEB / "downstream-v2.js").read_text(encoding="utf-8")
    assert "REVISION_EXAMPLES" in js
    assert "(answer.version || 1) === 1" in js, "the example must prefer an unrevised answer"
    assert 'select.value = targetId' in js


def test_every_question_has_a_worked_correction_to_offer():
    from downstream.collaboration import HEIGHT_CONFLICT_QUESTION
    from downstream.partner import QUESTION_BANK

    js = (WEB / "downstream-v2.js").read_text(encoding="utf-8")
    block = js[js.index("const REVISION_EXAMPLES"): js.index("function renderRevision")]
    for question in [*QUESTION_BANK, HEIGHT_CONFLICT_QUESTION]:
        assert question["id"] in block, f"no correction example for {question['id']}"


def test_the_correction_example_picks_the_same_answer_every_time():
    """A recording is one take, so the section that rewrites itself must be predictable."""
    js = (WEB / "downstream-v2.js").read_text(encoding="utf-8")
    assert "REVISION_ORDER" in js
    order_block = js[js.index("const REVISION_ORDER"): js.index("const REVISION_EXAMPLES")]
    assert order_block.index('"emergency_manager"') < order_block.index('"downstream_people"'), (
        "emergency_manager must be tried first so the Notification section is the one that changes"
    )


def test_the_brand_is_a_link_home_on_every_page():
    """It is the first thing anyone clicks to get back, and it was a div on all four pages."""
    for name in ("downstream.html", "developer.html",
                 "downstream-judges-v2.html", "downstream-evidence.html"):
        html = (WEB / name).read_text(encoding="utf-8")
        assert '<a class="brand" href="/"' in html, name
        assert 'aria-label="Downstream home"' in html, name


def test_the_interface_is_served_with_revalidation():
    """A cached script against fresh markup addresses elements that have moved.

    The pages and the script that drives them deploy together, and judging runs for a month
    against a URL that gets redeployed during it.
    """
    from fastapi.testclient import TestClient

    from service.main import app

    client = TestClient(app)
    for path in ("/", "/judges", "/developer", "/evidence", "/static/downstream-v2.js"):
        assert client.get(path).headers.get("cache-control") == "no-cache", path


def test_the_console_columns_are_capped_to_the_viewport():
    """The three columns exist to be read side by side. Past a screen height that stops working.

    Both sibling submissions cap the panel and scroll inside it rather than letting it push the
    page, and `min-height: 0` is the load-bearing half: without it a grid child will not shrink
    below its content and the max-height is ignored.
    """
    css = (WEB / "downstream-v2.css").read_text(encoding="utf-8")
    block = css[css.index("console height discipline"):]
    for token in ("min-height: 0", "overflow-y: auto", "calc(100vh", "overscroll-behavior: contain"):
        assert token in block, token


def test_the_context_meter_does_not_spend_three_lines_on_its_method():
    """It is a footnote. It sits in a 270px column where it cost more height than the number."""
    js = (WEB / "downstream-v2.js").read_text(encoding="utf-8")
    meter = js[js.index("const meter = workspace.context_meter"): js.index("function conflictEvidence")]
    assert 'title="' in meter, "the method should be a tooltip, not body copy"
    assert "<span>\" + text(meter.method)" not in meter


def test_the_correction_example_carries_an_identifier_so_the_boundary_is_visible():
    """The video claims the owner keeps the number and only a pseudonym crosses to a model.

    That has to be demonstrable on screen, not merely true of the system. The 555-01xx range is
    reserved for fiction, so putting one in the worked example is safe.
    """
    from downstream.partner import shield

    js = (WEB / "downstream-v2.js").read_text(encoding="utf-8")
    block = js[js.index("emergency_manager: {"):]
    block = block[: block.index("},")]
    assert "555-0142" in block, "the worked correction should contain a number"

    shielded = shield("After hours call the county duty desk on 406-555-0142, not the daytime office line.")
    assert "PHONE" in shielded["shapes"]
    assert "406-555-0142" not in shielded["text"]
    assert "PHONE_1" in shielded["text"]


def test_the_hidden_attribute_actually_hides():
    """`[hidden]` only carries display:none from the user-agent sheet, so `.profile-grid`
    setting `display: grid` beat it and the panel stayed on screen while the DOM property read
    true. Checking the property rather than the rendering is how that survived."""
    css = (WEB / "downstream-v2.css").read_text(encoding="utf-8")
    assert "[hidden] { display: none !important; }" in css


def test_a_cold_visitor_is_not_shown_six_empty_panels():
    """The scaffolding is evidence of a run. Before there is one it reported "nothing yet" in six
    places and pushed the one action worth taking below the fold."""
    html = (WEB / "downstream.html").read_text(encoding="utf-8")
    for hidden in ('id="console-shell" hidden', 'id="profile-grid" hidden', 'id="autonomy-pane" hidden'):
        assert hidden in html, hidden
    assert 'id="console-empty"' in html


def test_the_strongest_action_is_the_first_one_offered():
    html = (WEB / "downstream.html").read_text(encoding="utf-8")
    actions = html[html.index('class="workspace-actions"'):]
    actions = actions[: actions.index("</div>")]
    assert "Run the whole thing in one request" in actions
    assert actions.index("Run the whole thing") < actions.index("Answer the questions myself")
    assert 'class="btn-primary"' in actions.split("Run the whole thing")[0][-120:]


def test_every_entry_point_into_a_run_reveals_the_console():
    js = (WEB / "downstream-v2.js").read_text(encoding="utf-8")
    assert "function revealConsole()" in js
    # render() is the single funnel every path goes through.
    assert js.index("revealConsole();") > js.index("function render(workspace")
    for control in ("#run-top", "#run-empty", "#start-empty"):
        assert control in js, control


def test_the_run_says_what_it_is_doing_without_faking_progress():
    """The run is one server-side call the page cannot observe midway.

    Stating what was asked for is honest. Animating steps the page has not seen happen would be
    theatre, and the timeline underneath already reports the truth with real timestamps.
    """
    js = (WEB / "downstream-v2.js").read_text(encoding="utf-8")
    assert 'id="run-plan"' in (WEB / "downstream.html").read_text(encoding="utf-8")
    plan = js[js.index("async function runWholeThing"):]
    plan = plan[: plan.index('$("#arm-live-proof")')]
    assert "Running one request. It will:" in plan
    assert "read the 1958 drawing with Gemini" in plan


def test_the_timeline_opens_itself_and_names_each_step_in_plain_words():
    """Collapsed, the strongest evidence in the product was a number on a tile."""
    js = (WEB / "downstream-v2.js").read_text(encoding="utf-8")
    assert "STEP_TITLES" in js
    assert "wrap.open = true" in js
    for step, title in [
        ("drawing_read", "Read the 1958 drawing with Gemini"),
        ("source_conflict_detected", "Noticed two sources disagree"),
        ("paused_for_reserved_authority", "Stopped at owner knowledge"),
    ]:
        assert f'{step}: "{title}"' in js, step


def test_every_recorded_step_kind_has_a_plain_language_title():
    """A step with no title falls back to an identifier with the underscores taken out."""
    import re

    js = (WEB / "downstream-v2.js").read_text(encoding="utf-8")
    titled = set(re.findall(r"^  (\w+): \"", js[js.index("const STEP_TITLES"):], re.M))


    source = (Path(__file__).resolve().parents[1] / "downstream" / "autonomy.py").read_text(
        encoding="utf-8"
    )
    emitted = set(re.findall(r'record_step\(\s*workspace,\s*\w+,\s*"(\w+)"', source))
    emitted.add("unattended_review_ran")  # written by advance_on_wake, not record_step
    missing = {s for s in emitted if s and s not in titled}
    assert not missing, f"steps with no plain-language title: {sorted(missing)}"


def test_the_correction_loop_is_not_buried_in_a_scrolling_column():
    """It lived inside the middle pane, which scrolls to fit a viewport.

    That put the one control the judge path tells you to use below the fold of a region nobody
    had reason to think was scrollable. It is a full-width band under the three panes now.
    """
    html = (WEB / "downstream.html").read_text(encoding="utf-8")
    assert 'class="revision-dock"' in html

    shell = html[html.index('class="partner-shell"'): html.index('class="revision-dock"')]
    assert 'id="revision-card"' not in shell, "the correction card must sit outside the panes"

    dock = html[html.index('class="revision-dock"'):]
    assert 'id="revision-card"' in dock[: dock.index("</div>") + 400]


def test_the_correction_dock_does_not_split_labels_from_their_fields():
    """A two-column grid auto-placed each child into the next cell, so every label landed in one
    column and its own field in the other. Constraining width does the same job and cannot come
    apart; pairing them in a grid would need a wrapper per field."""
    css = (WEB / "downstream-v2.css").read_text(encoding="utf-8")
    dock = css[css.index(".revision-dock {"):]
    assert "grid-template-columns" not in dock.split("@media (max-width")[0]
