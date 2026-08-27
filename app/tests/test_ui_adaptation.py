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
    for hidden in ('id="console-shell" hidden', 'id="autonomy-pane" hidden'):
        assert hidden in html, hidden
    assert 'id="console-empty"' in html


def test_the_learned_profile_is_a_named_section_of_the_receipt():
    """It was a bare strip of seven tiles floating between two titled cards.

    Nothing said what they were, and three of the seven announced that nothing had been learned
    yet -- rendered at the same size and weight as "15 automatic steps", which told a reader the
    absence of a preference mattered as much as the evidence of a run.
    """
    html = (WEB / "downstream.html").read_text(encoding="utf-8")
    js = (WEB / "downstream-v2.js").read_text(encoding="utf-8")

    receipt = html[html.index('id="autonomy-pane"'):]
    receipt = receipt[: receipt.index("</article>")]
    assert 'id="profile-grid"' in receipt, "the learned profile belongs inside the receipt card"
    assert "What it learned about you" in receipt, "the tiles need a stated subject"

    profile = js[js.index("function renderProfile"):js.index("function updatePersistentControls")]
    assert '!== "standard"' in profile, "defaults must not be rendered as learned preferences"
    assert "learned-note" in profile, "the empty state needs one sentence, not three empty tiles"


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


def test_the_run_log_shows_the_newest_step_and_hides_the_rest_behind_one_control():
    """Twenty-three steps expanded ran to two screens and buried everything under the receipt.

    The newest step is what the page owes a reader at a glance. The full log stays one arrow away,
    because the reader who wants to audit twenty-three steps is willing to click once for them.
    """
    js = (WEB / "downstream-v2.js").read_text(encoding="utf-8")
    html = (WEB / "downstream.html").read_text(encoding="utf-8")
    assert "STEP_TITLES" in js
    assert 'id="autonomy-latest"' in html, "the newest step needs its own list"
    assert "wrap.open = true" not in js, "the log must not expand itself again"
    # The collapsed state is the default, and only the label and newest step are refreshed after
    # that -- re-closing on every render would collapse the log under a reader who just opened it.
    assert "syncRunLog" in js
    for step, title in [
        ("drawing_read", "Read the 1958 drawing with Gemini"),
        ("source_conflict_detected", "Noticed two sources disagree"),
        ("paused_for_reserved_authority", "Stopped at owner knowledge"),
    ]:
        assert f'{step}: "{title}"' in js, step


def test_every_titled_step_also_says_why_it_exists():
    """The stored detail says what happened; a reader still cannot tell why the step exists.

    That rationale is what separates a designed agent from a sequence of calls, and it is the one
    thing a judge cannot reconstruct from an identifier.
    """
    import re

    js = (WEB / "downstream-v2.js").read_text(encoding="utf-8")
    titled = set(re.findall(r"^  (\w+):", js[js.index("const STEP_TITLES"):js.index("const STEP_LABELS")], re.M))
    explained = set(re.findall(r"^  (\w+):", js[js.index("const STEP_WHY"):js.index("function stepMarkup")], re.M))
    assert not titled - explained, f"steps with no rationale: {sorted(titled - explained)}"


def test_the_correction_card_stays_on_the_answer_it_just_revised():
    """Saving re-renders the card, and a rebuilt <select> defaults to its first option.

    That walked the card off the answer just corrected: the history control dropped back to
    "View 1 saved version" for an unrelated question, at the exact moment it is meant to prove
    both versions were kept.
    """
    js = (WEB / "downstream-v2.js").read_text(encoding="utf-8")
    assert "lastRevised: null" in js, "the held selection needs a declared home on state"
    revise = js[js.index("async function reviseSelectedAnswer"):]
    assert "state.lastRevised = questionId" in revise[: revise.index("\n}")], (
        "the revised question must be recorded before the re-render"
    )
    render = js[js.index("function renderRevision"):js.index("function renderProfile")]
    assert "state.lastRevised" in render and "selected" in render, (
        "renderRevision must re-select the held answer when it rebuilds the options"
    )
    reset = js[js.index("function resetDemo"):js.index('$("#arm-live-proof").addEventListener')]
    assert "state.lastRevised = null" in reset, "a cleared console must not hold a dead selection"


def test_a_bare_home_url_always_opens_at_the_top():
    """The brand links to "/", and the console lives on "/", so the brand is often a link to the
    page you are already on. A browser that treats that as a reload restores the old scroll
    position, and the front door opens halfway down the page."""
    js = (WEB / "downstream-v2.js").read_text(encoding="utf-8")
    boot = js[js.index("initTheme();"):]
    assert 'history.scrollRestoration = "manual"' in boot
    assert "window.scrollTo(0, 0)" in boot
    assert "!window.location.hash" in boot, "an explicit anchor must still be honoured"
    for page in ("downstream.html", "developer.html", "downstream-judges-v2.html", "downstream-evidence.html"):
        assert '<a class="brand" href="/"' in (WEB / page).read_text(encoding="utf-8"), page


def test_start_over_clears_the_counts_it_is_clearing_the_run_for():
    """Leaving 15 automatic steps on a cleared console would be a count for a run that is gone."""
    js = (WEB / "downstream-v2.js").read_text(encoding="utf-8")
    assert 'id="reset-demo"' in (WEB / "downstream.html").read_text(encoding="utf-8")
    reset = js[js.index("function resetDemo"):js.index('$("#arm-live-proof").addEventListener')]
    for cleared in ["#autonomy-timeline", "#autonomy-latest", "#autonomy-grid", "#console-empty"]:
        assert cleared in reset, cleared
    assert 'searchParams.delete("workspace")' in reset, "a cleared console must drop the resume id"


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
    """A bare two-column grid auto-placed each child into the next cell, so every label landed in
    one column and its own field in the other.

    The card is two columns again -- form left, saved versions right -- but the form is a single
    grid child now, so a label physically cannot be separated from the input it names.
    """
    css = (WEB / "downstream-v2.css").read_text(encoding="utf-8")
    js = (WEB / "downstream-v2.js").read_text(encoding="utf-8")

    body = css[css.index(".revision-body {"):]
    assert "grid-template-columns" in body.split("}")[0], "the dock uses both halves of its width"
    assert ".revision-form {" in css, "the form must be one grid child, not a pile of them"

    markup = js[js.index('$("#revision-card").innerHTML'):js.index('const select = $("#revision-question")')]
    form = markup[markup.index('class="revision-form"'):markup.index('class="revision-side"')]
    for field in ("revision-question", "revision-answer", "revision-reason", "save-revision"):
        assert field in form, f"{field} escaped the form wrapper and can be split from its label"


def test_the_completed_column_shows_the_facts_instead_of_white_space():
    """With no question left, the middle column held a short card and ~500px of nothing, dead
    centre of the page. The quoted facts are the most concrete evidence the console has, and they
    used to disappear the moment the workflow finished."""
    js = (WEB / "downstream-v2.js").read_text(encoding="utf-8")
    assert "function groundedFactsMarkup" in js
    facts = js[js.index("function groundedFactsMarkup"):js.index("function renderQuestion")]
    assert "quoted_text" in facts, "a value without its quote is the thing this project refuses"
    assert "conflicts_with" in facts, "the 28-vs-31 disagreement has to survive completion"
    complete = js[js.index('<span class="eyebrow">Question set complete'):]
    assert "groundedFactsMarkup(workspace)" in complete[:900]
