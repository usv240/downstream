const state = {
  workspace: null,
  guided: new URLSearchParams(window.location.search).get("guided") === "1",
  busy: false,
  // The answer most recently corrected, so the correction card stays on it across the re-render
  // that saving triggers rather than snapping back to the first option.
  lastRevised: null,
};

const DEMO_ANSWERS = {
  access_heavy_rain: "The gravel lane washes out at the second bend during sustained rain.",
  emergency_manager: "Call Jordan Lee at the Example County desk, then the after-hours dispatch line.",
  downstream_people: "Two seasonal cabins, a riverside campsite, and livestock are below the dam.",
  spillway_history: "Water crossed the overflow channel in 2019 without reaching the access road.",
  equipment: "The county public works loader is about 25 minutes away when the east road is open.",
  resolve_dam_height_conflict: "Retain both values until the qualified engineer confirms the controlling record.",
};

const QUESTION_LABELS = [
  ["access_heavy_rain", "Access"],
  ["emergency_manager", "Emergency contact"],
  ["downstream_people", "Downstream knowledge"],
  ["spillway_history", "History"],
  ["equipment", "Resources"],
  ["resolve_dam_height_conflict", "Source conflict"],
];

const $ = (selector) => document.querySelector(selector);

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || response.status + " " + response.statusText);
  }
  return response.json();
}

function text(value) {
  const node = document.createElement("span");
  node.textContent = value == null ? "" : String(value);
  return node.innerHTML;
}

function setStatus(message, tone = "neutral") {
  const box = $("#app-status");
  // Collapsed until there is something to report. It stays in the DOM so the live region is
  // present before it is updated, which is what screen readers need, but an empty status bar
  // repeating the invitation directly beneath it is just another panel saying nothing yet.
  box.className = "app-status " + tone + (message ? "" : " is-idle");
  box.textContent = message;
}

function setBusy(busy) {
  state.busy = busy;
  document.documentElement.classList.toggle("is-busy", busy);
  document.querySelectorAll("[data-action]").forEach((control) => {
    control.disabled = busy;
  });
  if (!busy) updatePersistentControls();
}

async function runAction(message, action, success, options = {}) {
  if (state.busy) return;
  setBusy(true);
  setStatus(message, "working");
  try {
    const result = await action();
    if (result && result.workspace_id) render(result, { focusQuestion: options.focusQuestion !== false });
    setStatus(typeof success === "function" ? success(result) : success, "success");
    return result;
  } catch (error) {
    setStatus(error.message || "The request could not be completed. Try again.", "error");
    return null;
  } finally {
    setBusy(false);
  }
}

function workspaceLink(workspaceId) {
  const url = new URL(window.location.href);
  url.searchParams.set("workspace", workspaceId);
  if (state.guided) url.searchParams.set("guided", "1");
  url.hash = "workspace";
  return url;
}

function syncWorkspaceIdentity(workspace) {
  const url = workspaceLink(workspace.workspace_id);
  window.history.replaceState({}, "", url);
  $("#workspace-code").textContent = workspace.workspace_id;
  $("#resume-url").href = url.toString();
  $("#workspace-identity").hidden = false;
}

function renderProgress(workspace) {
  const progress = workspace.progress;
  $("#progress-copy").textContent =
    progress.answered + " answered, " + progress.skipped + " held for later, " + progress.total + " total.";

  $("#progress-list").innerHTML = QUESTION_LABELS.map(([id, label], index) => {
    const answered = Object.hasOwn(workspace.answers, id);
    const held = workspace.skipped.includes(id);
    const current = workspace.next_question && workspace.next_question.id === id;
    const className = answered ? "done" : held ? "held" : current ? "current" : "";
    const marker = answered ? "OK" : held ? "Held" : index + 1;
    const currentAttr = current ? ' aria-current="step"' : "";
    return '<li class="' + className + '"' + currentAttr + '><span class="mark">' +
      marker + '</span><span>' + label + '</span></li>';
  }).join("");

  const meter = workspace.context_meter;
  const pct = Math.min(100, Math.round((meter.structured_context_tokens / meter.bound) * 100));
  // The comparison is the point, not the absolute number. A bounded context is only interesting
  // against what the naive alternative would have cost, so show both and the multiple.
  const saved = meter.estimated_transcript_replay_tokens;
  const times = saved && meter.structured_context_tokens
    ? (saved / meter.structured_context_tokens).toFixed(1)
    : null;
  $("#context-meter").innerHTML =
    "<b>" + meter.structured_context_tokens + " / " + meter.bound + " tokens</b>" +
    '<div class="meter"><div class="meter-track" role="meter" aria-label="Structured context use" aria-valuemin="0" aria-valuemax="' +
    meter.bound + '" aria-valuenow="' + meter.structured_context_tokens + '"><div class="meter-fill" style="width:' +
    pct + '%"></div></div>' +
    (times
      ? '<span class="context-compare" title="' + text(meter.method) + '"><b>' + times +
        "&times; smaller</b> than replaying the transcript</span>"
      : "") +
    "</div>";
}

function conflictEvidence(question) {
  if (!question.evidence) return "";
  return '<div class="source-compare" aria-label="Conflicting retrieved values">' +
    '<div><small>Registry fixture</small><b>' + text(question.evidence.conflicts_with) + '</b></div>' +
    '<div><small>Legacy drawing</small><b>' + text(question.evidence.drawing_value) + " ft</b>" +
    '<span>' + text(question.evidence.drawing_quote) + '</span></div></div>';
}

const FACT_LABELS = {
  crest_elevation: "Crest elevation",
  spillway: "Spillway",
  dam_height_ft: "Dam height",
};

// After the last question the middle column had nothing left to say, and left roughly 500px of
// white in the visual centre of the page. These are the facts the run lifted off the drawing,
// each with the quote it came from -- the most concrete evidence the console holds, and until
// now it vanished the moment the workflow finished.
function groundedFactsMarkup(workspace) {
  // The disagreement leads. Filling this column pushed it to third of three, below the fold of a
  // pane that scrolls inside itself -- the same way the mapping gate got buried, and the same fix.
  // A value two sources argue about is worth more than two they agree on.
  const facts = (workspace.facts || [])
    .filter((fact) => fact.quoted_text)
    .sort((a, b) => Number(Boolean(b.conflicts_with)) - Number(Boolean(a.conflicts_with)));
  if (!facts.length) return "";
  return '<section class="grounded"><h4>What it read, and what it can quote</h4>' +
    facts.map((fact) => {
      const label = FACT_LABELS[fact.key] || String(fact.key || "").replaceAll("_", " ");
      const source = String(fact.provenance || "").startsWith("live_")
        ? "Gemini 3.5 Flash, live"
        : "graded recording";
      const conflict = fact.conflicts_with
        ? '<span class="grounded-conflict">Disagrees with the ' + text(fact.conflicts_with) + "</span>"
        : "";
      return '<article class="grounded-fact"><div class="grounded-head"><small>' + text(label) +
        "</small><b>" + text(fact.value) + "</b></div>" +
        "<q>" + text(fact.quoted_text) + "</q>" +
        '<span class="grounded-src">' + text(source) + "</span>" + conflict + "</article>";
    }).join("") + "</section>";
}

function renderQuestion(workspace) {
  const question = workspace.next_question;
  if (!question) {
    const held = workspace.skipped.length;
    const action = held
      ? '<button id="resume-session" data-action type="button">Review ' + held + ' held question' + (held === 1 ? "" : "s") + '</button>'
      : '<button id="resume-session" data-action type="button">Open another saved session</button>';
    $("#question-card").innerHTML =
      '<span class="eyebrow">Question set complete</span>' +
      '<h3 id="current-question-heading" tabindex="-1">The review draft is ready.</h3>' +
      '<p>Five facts came from the owner and one disagreement between two sources is on record, ' +
      'each with where it came from. The flood map stays blocked until a qualified engineer signs off.</p>' +
      '<div class="completion-checks"><span>Owner facts structured</span><span>Conflict retained</span><span>Unsafe map withheld</span></div>' +
      '<div class="btn-row">' + action + '<a class="btn" href="/evidence">Open evidence dashboard</a></div>' +
      groundedFactsMarkup(workspace);
    $("#resume-session").addEventListener("click", resumeSession);
    return;
  }

  const basis = question.basis === "unresolved_source_conflict"
    ? '<span class="basis-badge conflict">Retrieved sources disagree</span>'
    : '<span class="basis-badge">Missing owner fact</span>';
  const guided = state.guided
    ? '<div class="guided-callout"><b>Guided step</b><span>Use the example, save, watch the draft update.</span></div>'
    : "";
  $("#question-card").innerHTML =
    '<div class="question-meta"><span>Question ' + question.position + " of " + question.total + '</span>' +
    '<span>For ' + text(question.section) + '</span></div>' + basis +
    '<h3 id="current-question-heading" tabindex="-1">' + text(question.text) + '</h3>' +
    '<p class="muted small" id="question-help">Why I am asking: ' + text(question.why) + '</p>' +
    (question.gloss ? '<p class="gloss"><b>Plain meaning:</b> ' + text(question.gloss) + '</p>' : "") +
    conflictEvidence(question) + guided +
    '<label for="owner-answer" class="control-kicker">Your answer</label>' +
    '<textarea class="control" id="owner-answer" rows="4" aria-describedby="question-help answer-error" placeholder="Use the words you would normally use."></textarea>' +
    '<p class="field-error" id="answer-error"></p>' +
    '<div class="btn-row"><button class="btn-primary" data-action type="button" id="answer-question">Save and continue</button>' +
    '<button data-action type="button" id="example-answer">Use synthetic example</button>' +
    '<button data-action type="button" id="unknown-question">Explain this more simply</button>' +
    '<button data-action type="button" id="skip-question">Hold for later</button></div>';

  $("#answer-question").addEventListener("click", () => answer(false));
  $("#example-answer").addEventListener("click", () => {
    $("#owner-answer").value = DEMO_ANSWERS[question.id] || "Synthetic owner fact for review.";
    $("#owner-answer").focus();
    setStatus("Synthetic example inserted. Review it, then save and continue.", "neutral");
  });
  $("#unknown-question").addEventListener("click", () => answer(true));
  $("#skip-question").addEventListener("click", skip);
}

// What an evidence kind means to a reader, where the identifier alone would not say.
const EVIDENCE_KIND_LABELS = {
  fail_closed_mapping_policy: "Stopped on purpose, not by error",
};

function renderPlan(workspace) {
  const ledger = new Map(workspace.evidence_ledger.map((row) => [row.section, row]));
  $("#plan-stack").innerHTML = workspace.plan.map((section) => {
    const evidence = ledger.get(section.key)?.evidence || [];
    const evidenceKinds = [...new Set(evidence.map((item) => EVIDENCE_KIND_LABELS[item.kind] || item.kind.replaceAll("_", " ")))];
    const evidenceLabel = evidenceKinds.length ? evidenceKinds.join(" + ") : "unresolved gap";
    return '<article class="plan-section"><h4>' + text(section.title) + '</h4><p>' + text(section.text) + '</p>' +
      '<div class="section-meta"><span class="section-status ' + section.status + '">' +
      text(section.status.replaceAll("_", " ")) + '</span><span class="evidence-chip">' +
      text(evidenceLabel) + '</span></div>' +
      (section.source ? '<p><a href="' + section.source.url + '">' + text(section.source.source) + '</a></p>' : "") +
      '</article>';
  }).join("");
}

function historyMarkup(answer) {
  const count = answer.history.length;
  return '<h4>' + count + " saved version" + (count === 1 ? "" : "s") + "</h4>" +
    '<ol class="version-list">' +
    answer.history.map((entry) => '<li><b>Version ' + entry.version + '</b><span>' +
      text(entry.answer) + '</span><small>' + text(entry.reason) + '</small></li>').join("") +
    "</ol>";
}

// Per-question corrections, so the example rewrites a section a viewer can watch change rather
// than restating what is already there.
// Tried in this order. emergency_manager leads because an after-hours contact is the most
// legible thing to watch a draft section rewrite itself around.
const REVISION_ORDER = [
  "emergency_manager",
  "access_heavy_rain",
  "downstream_people",
  "spillway_history",
  "equipment",
  "resolve_dam_height_conflict",
];

const REVISION_EXAMPLES = {
  access_heavy_rain: {
    answer: "The east lane washes out at the second bend.",
    reason: "Owner corrected the access location.",
  },
  emergency_manager: {
    // Carries a number on purpose. The 555-01xx range is reserved for fiction, so this is safe to
    // put on screen, and it makes the redaction boundary visible rather than merely asserted: the
    // owner keeps the digits, the model-safe form of the same answer carries PHONE_1.
    answer: "After hours call the county duty desk on 406-555-0142, not the daytime office line.",
    reason: "Owner corrected the after-hours contact.",
  },
  downstream_people: {
    answer: "The campground below the spillway is occupied from May to September.",
    reason: "Owner narrowed the season.",
  },
  spillway_history: {
    answer: "Water topped the channel in 1998 and cut a gully on the left abutment.",
    reason: "Owner corrected the year.",
  },
  equipment: {
    answer: "The neighbouring farm's excavator is about forty minutes away.",
    reason: "Owner corrected the travel time.",
  },
  resolve_dam_height_conflict: {
    answer: "Our insurance file uses 28 feet; the state engineer should confirm the drawing.",
    reason: "Owner named who resolves it.",
  },
};

function renderRevision(workspace) {
  const answers = Object.entries(workspace.answers);
  if (!answers.length) {
    $("#revision-card").innerHTML =
      '<span class="eyebrow">Correction loop</span><h3>Your corrections stay attributable.</h3>' +
      '<p class="muted small">After the first answer, revise it here. Downstream keeps both versions and updates the draft.</p>';
    return;
  }

  // Saving a correction re-renders this card from scratch, and a rebuilt <select> falls back to
  // its first option. That walked the card away from the answer just corrected: the history
  // control dropped back to "View 1 saved version" for an unrelated question, so the one control
  // that proves both versions were kept was showing the wrong one at the moment it mattered.
  const held = state.lastRevised && workspace.answers[state.lastRevised] ? state.lastRevised : null;
  const options = answers.map(([id, answer]) =>
    '<option value="' + id + '"' + (id === held ? " selected" : "") + ">" +
    text(id.replaceAll("_", " ")) + ", version " + answer.version + "</option>"
  ).join("");
  $("#revision-card").innerHTML =
    '<span class="eyebrow">Correction loop</span><h3>Change an owner fact without erasing history.</h3>' +
    '<div class="revision-body">' +
    '<div class="revision-form">' +
    '<label for="revision-question" class="control-kicker">Answer to revise</label>' +
    '<select class="control" id="revision-question">' + options + '</select>' +
    '<label for="revision-answer" class="control-kicker">Corrected answer</label>' +
    '<textarea class="control" id="revision-answer" rows="3"></textarea>' +
    '<label for="revision-reason" class="control-kicker">Why it changed</label>' +
    '<input class="control" id="revision-reason" value="Owner correction after review">' +
    '<p class="field-error" id="revision-error"></p>' +
    '<div class="btn-row"><button id="save-revision" data-action type="button">Revise and preserve history</button>' +
    (state.guided ? '<button id="example-revision" data-action type="button">Use correction example</button>' : "") +
    "</div></div>" +
    '<aside class="revision-side" id="revision-history"></aside>' +
    "</div>";

  const select = $("#revision-question");
  const fillCurrent = () => {
    const answer = workspace.answers[select.value];
    $("#revision-answer").value = answer.answer;
    $("#revision-history").innerHTML = historyMarkup(answer);
  };
  select.addEventListener("change", fillCurrent);
  fillCurrent();
  $("#save-revision").addEventListener("click", reviseSelectedAnswer);
  if ($("#example-revision")) {
    $("#example-revision").addEventListener("click", () => {
      // Pick an answer that has not been revised yet. The example used to be pinned to
      // access_heavy_rain, which the one-request run already corrects internally -- so using it
      // produced a third version with identical text and no visible change to the draft. A
      // correction that changes nothing on screen is worse than no example at all.
      // Deterministic order, not "whichever came first". A recording is one take, so the
      // section that visibly rewrites itself has to be the same one every rehearsal.
      const unrevised = (id) => {
        const answer = workspace.answers[id];
        return answer && (answer.version || 1) === 1;
      };
      const preferred = REVISION_ORDER.find(unrevised);
      const targetId =
        preferred || (answers.find(([, a]) => (a.version || 1) === 1) || answers[0])[0];
      select.value = targetId;
      fillCurrent();
      const example = REVISION_EXAMPLES[targetId] || {
        answer: "A corrected version of this answer.",
        reason: "Owner corrected this after review.",
      };
      $("#revision-answer").value = example.answer;
      $("#revision-reason").value = example.reason;
      setStatus("Correction example inserted. Save it to prove versioned adaptation.", "neutral");
    });
  }
}

function renderProfile(workspace) {
  const profile = workspace.profile;
  const adaptation = workspace.adaptation;

  // Only what has actually been learned. This used to render "standard", "standard" and "No
  // preferences yet" as three tiles the same size and weight as "15 automatic steps", which told
  // a reader the absence of a preference mattered as much as the evidence of a run -- seven
  // tiles, three of them announcing that nothing had happened yet.
  const learned = [];
  if (profile.reading_level && profile.reading_level !== "standard") {
    learned.push(["Reading level", profile.reading_level]);
  }
  if (profile.detail_preference && profile.detail_preference !== "standard") {
    learned.push(["Detail style", profile.detail_preference]);
  }
  const vocabulary = Object.entries(profile.vocabulary || {});
  if (vocabulary.length) {
    learned.push(["Vocabulary", vocabulary.map(([formal, preferred]) => formal + " → " + preferred).join(", ")]);
  }

  const tiles = learned.concat([
    ["Sessions remembered", adaptation.sessions_remembered],
    ["Feedback events", adaptation.feedback_events],
    ["Answer revisions", adaptation.answer_revisions],
    ["Source conflicts surfaced", adaptation.source_conflicts_surfaced],
  ]);
  $("#profile-grid").innerHTML = tiles
    .map(([label, value]) =>
      '<div class="profile-item"><small>' + text(label) + "</small><b>" + text(value) + "</b></div>")
    .join("");

  // One honest line instead of three tiles saying nothing. It also tells the reader which two
  // controls put something here, which the tiles never did.
  const note = $("#learned-note");
  if (note) note.hidden = learned.length > 0;
  updatePersistentControls();
}

function updatePersistentControls() {
  const enabled = Boolean(state.workspace) && !state.busy;
  $("#accept-plan").disabled = !enabled;
  $("#less-detail").disabled = !enabled;
}

// The stored step name is an identifier. This is what it means, in the product's own words.
const STEP_TITLES = {
  run_triggered: "A run was triggered",
  registry_record_resolved: "Resolved the dam record",
  drawing_read: "Read the 1958 drawing with Gemini",
  untrusted_spans_quarantined: "Quarantined instruction-shaped text",
  facts_grounded: "Grounded every fact in a quote",
  source_conflict_detected: "Noticed two sources disagree",
  mapping_gate_applied: "Applied the mapping gate",
  durable_wakes_registered: "Scheduled its own follow-ups",
  paused_for_reserved_authority: "Stopped at owner knowledge",
  owner_answer_recorded: "Owner supplied a fact",
  sections_recomposed: "Recomposed the affected sections",
  owner_correction_applied: "Owner corrected an answer",
  held_questions_reopened: "Reopened a held question",
  held_questions_reviewed: "Checked for held questions",
  follow_up_recorded: "Recorded a follow-up",
  unattended_review_ran: "Reviewed the draft unattended",
};

const STEP_LABELS = {
  agent: "Agent",
  human_authority: "Owner authority",
  external_evidence: "External event",
};

// The stored timeline says *what* happened and the server's own detail line says *how*. Neither
// says why the step exists, which is the part a reader cannot infer from an identifier and the
// part that separates a designed agent from a sequence of calls. This is design rationale, fixed
// per step kind -- it never asserts anything about a particular run.
const STEP_WHY = {
  run_triggered:
    "An external event opened this run, not an operator pressing start. That is the line between an agent and a tool you drive.",
  registry_record_resolved:
    "Anything already recorded somewhere is the agent's job to fetch. Asking the owner to retype it would be the failure.",
  drawing_read:
    "A dam's real dimensions live on a scanned sheet, not in a database. Reading it multimodally is the only way to get them without asking a person.",
  untrusted_spans_quarantined:
    "A scanned document is untrusted input. Anything shaped like an instruction is stripped before the text is allowed near a model.",
  facts_grounded:
    "Every fact kept carries the quote it came from, so a reviewer can check it rather than trust it.",
  source_conflict_detected:
    "Two sources disagreeing is exactly what a language model papers over. It raises a question instead of quietly choosing a number.",
  mapping_gate_applied:
    "Inundation extent needs a qualified engineer. The gate fails closed rather than produce a map that would look authoritative and not be.",
  durable_wakes_registered:
    "Follow-ups are written to the database, not held in memory, so they survive the process exiting and fire whether or not anyone is watching.",
  paused_for_reserved_authority:
    "Some knowledge exists only in the owner's head. Inventing it is the one failure this product refuses, so the run stops here instead.",
  owner_answer_recorded:
    "Recorded as owner authority, never as agent output. The receipt keeps the two apart so the counts above cannot be inflated.",
  sections_recomposed:
    "New evidence rewrites the affected sections immediately. Nobody has to ask for a rebuild or notice that one is needed.",
  owner_correction_applied:
    "The previous answer is kept as a version rather than overwritten, so a correction stays auditable a year later.",
  held_questions_reopened:
    "A question set aside comes back on schedule. Without this, holding a question would mean losing it.",
  held_questions_reviewed:
    "The scheduled check ran and found nothing outstanding. A no-op, still recorded, because an unlogged check proves nothing.",
  follow_up_recorded:
    "Written into the workspace for the owner's return. Nothing is sent to any person or agency on the agent's own authority.",
  unattended_review_ran:
    "This one fired on the wall clock with no browser open. It is the step that cannot be faked by a page you are looking at.",
};

// The steps a reader needs to see to know what ran. Collapsed, the receipt headlined only the
// newest step, which is the least interesting of the twenty-three: a follow-up note. These are the
// decisions -- the drawing read, the disagreement, the refusal, the stop -- in the order they
// happened, each coloured by who made it.
const HIGHLIGHT_STEPS = [
  "drawing_read",
  "untrusted_spans_quarantined",
  "source_conflict_detected",
  "mapping_gate_applied",
  "durable_wakes_registered",
  "paused_for_reserved_authority",
  "owner_correction_applied",
  "unattended_review_ran",
];

function highlightsMarkup(timeline) {
  const seen = new Set();
  return timeline
    .filter((entry) => HIGHLIGHT_STEPS.includes(entry.step) && !seen.has(entry.step) && seen.add(entry.step))
    .map((entry) => {
      const timing = entry.step === "drawing_read" ? (String(entry.detail || "").match(/in ([\d.]+s)/) || [])[1] : null;
      return '<li class="highlight ' + entry.actor + '"><b>' + text(STEP_LABELS[entry.actor] || entry.actor) + "</b>" +
        "<span>" + text(STEP_TITLES[entry.step] || entry.step.replaceAll("_", " ")) + (timing ? " · " + text(timing) : "") + "</span></li>";
    })
    .join("");
}

function offsetLabel(seconds) {
  if (seconds < 60) return seconds.toFixed(1) + "s";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return "+" + minutes + "m " + Math.round(seconds % 60) + "s";
  const hours = Math.floor(minutes / 60);
  const days = Math.floor(hours / 24);
  if (days >= 1) return "+" + days + "d " + (hours % 24) + "h";
  return "+" + hours + "h " + (minutes % 60) + "m";
}

function stepMarkup(entry, index, started) {
  // Elapsed since the trigger. The run takes about six seconds and a reader deserves to see
  // where each step fell inside it, rather than a flat list that could have been written by
  // hand afterwards.
  const at = Date.parse(entry.at);
  const offset = started && !Number.isNaN(at) ? offsetLabel((at - started) / 1000) : "";
  const why = STEP_WHY[entry.step];
  return (
    '<li class="timeline-step ' + entry.actor + '" data-step="' + text(entry.step) + '">' +
    '<span class="step-n">' + (index + 1) + "</span>" +
    "<b>" + text(STEP_LABELS[entry.actor] || entry.actor) + "</b>" +
    '<span class="step-at">' + text(offset) + "</span>" +
    '<span class="step-what">' + text(STEP_TITLES[entry.step] || entry.step.replaceAll("_", " ")) + "</span>" +
    '<span class="step-detail">' + text(entry.detail) + "</span>" +
    (why ? '<span class="step-why">' + text(why) + "</span>" : "") +
    "</li>"
  );
}

// Expanded, twenty-three steps ran to about two screens and pushed everything below the receipt
// out of reach, so the page read as a wall rather than as evidence. Collapsed to the newest step,
// the receipt stays one screen and the full log is one arrow away for anyone who wants to audit
// it -- which is the reader this list was always for.
function syncRunLog(wrap, count) {
  const open = wrap.open;
  wrap.querySelector("summary").textContent = open
    ? "Hide the earlier steps"
    : "View all " + count + " steps, in the order they happened";
  ["#autonomy-latest", "#run-log-eyebrow", "#autonomy-highlights", "#run-log-latest-label"].forEach((s) => {
    const node = $(s);
    if (node) node.hidden = open;
  });
}

function renderAutonomy(workspace) {
  const proof = workspace.autonomy_proof;
  if (!proof) return;
  const tiles = [
    ["Steps it took on its own", proof.automatic_agent_steps],
    ["Facts only the owner could give", proof.human_authority_steps],
    ["Clicks needed to keep it going", proof.continue_clicks_required],
    ["Follow-ups it scheduled for itself", proof.durable_wakes_registered],
  ];
  $("#autonomy-grid").innerHTML = tiles
    .map(([label, value]) =>
      '<div class="profile-item"><small>' + text(label) + "</small><b>" + text(value) + "</b></div>")
    .join("");
  $("#autonomy-waiting").textContent =
    "Trigger: " + proof.trigger.replaceAll("_", " ") + ". Now waiting on " +
    String(proof.waiting_on).replaceAll("_", " ") + ".";
  const timeline = proof.timeline || [];
  const started = timeline.length ? Date.parse(timeline[0].at) : 0;
  $("#autonomy-timeline").innerHTML = timeline
    .map((entry, index) => stepMarkup(entry, index, started))
    .join("");
  const last = timeline.length - 1;
  $("#autonomy-highlights").innerHTML = highlightsMarkup(timeline);
  $("#autonomy-latest").innerHTML = last >= 0 ? stepMarkup(timeline[last], last, started) : "";
  const wrap = $("#autonomy-timeline-wrap");
  if (wrap && timeline.length) {
    if (!wrap.dataset.wired) {
      wrap.dataset.wired = "1";
      wrap.addEventListener("toggle", () => syncRunLog(wrap, Number(wrap.dataset.count || 0)));
    }
    // Only the label and the newest step are refreshed here. Re-closing the log on every render
    // would collapse it under a reader who had just opened it -- and the unattended wake lands
    // mid-session by design, so that would happen at the least predictable moment.
    wrap.dataset.count = String(timeline.length);
    syncRunLog(wrap, timeline.length);
  }
}

function revealConsole() {
  // The scaffolding is evidence of a run. Before there is one it was six panels each saying
  // "nothing yet", which is a lot of furniture for no information and buried the one action
  // worth taking.
  const empty = $("#console-empty");
  if (empty) empty.hidden = true;
  ["#console-shell", "#autonomy-pane"].forEach((selector) => {
    const node = $(selector);
    if (node) node.hidden = false;
  });
}

function render(workspace, options = {}) {
  revealConsole();
  state.workspace = workspace;
  syncWorkspaceIdentity(workspace);
  renderProgress(workspace);
  renderQuestion(workspace);
  renderPlan(workspace);
  renderRevision(workspace);
  renderProfile(workspace);
  renderAutonomy(workspace);
  if (options.focusQuestion) {
    window.requestAnimationFrame(() => $("#current-question-heading")?.focus());
  }
}

async function start() {
  return runAction(
    "Creating a clean synthetic workspace.",
    () => api("/downstream/workspaces", { method: "POST", body: "{}" }),
    state.guided
      ? "Guided workspace ready. Use the synthetic example and save each answer."
      : "Synthetic workspace ready. Your resume link is now visible."
  );
}

async function restore(workspaceId) {
  return runAction(
    "Restoring the saved workspace.",
    () => api("/downstream/workspaces/" + encodeURIComponent(workspaceId)),
    "Saved workspace restored with its answers, revisions, and adaptation profile.",
    { focusQuestion: false }
  );
}

async function answer(didNotUnderstand) {
  const question = state.workspace.next_question;
  const answerBox = $("#owner-answer");
  const answerText = answerBox.value.trim();
  if (!didNotUnderstand && !answerText) {
    answerBox.setAttribute("aria-invalid", "true");
    $("#answer-error").textContent = "Enter an answer, use the synthetic example, or hold this question for later.";
    answerBox.focus();
    setStatus("This question still needs an answer or an explicit hold.", "error");
    return;
  }
  answerBox.removeAttribute("aria-invalid");
  $("#answer-error").textContent = "";

  await runAction(
    didNotUnderstand ? "Rephrasing this question." : "Saving the owner fact and updating the draft.",
    () => api("/downstream/workspaces/" + state.workspace.workspace_id + "/answer", {
      method: "POST",
      body: JSON.stringify({
        question_id: question.id,
        answer: answerText || "Please explain this term.",
        did_not_understand: didNotUnderstand,
      }),
    }),
    didNotUnderstand
      ? "The same question is now in plain language with a definition."
      : "Owner fact saved. The draft and evidence ledger are updated."
  );
}

async function reviseSelectedAnswer() {
  const questionId = $("#revision-question").value;
  const revisedAnswer = $("#revision-answer").value.trim();
  const reason = $("#revision-reason").value.trim();
  if (!revisedAnswer || !reason) {
    $("#revision-error").textContent = "Provide both the corrected answer and why it changed.";
    setStatus("The correction needs an answer and a reason.", "error");
    return;
  }
  $("#revision-error").textContent = "";
  state.lastRevised = questionId;
  await runAction(
    "Saving the correction and preserving the prior version.",
    () => api("/downstream/workspaces/" + state.workspace.workspace_id + "/answers/" + questionId + "/revise", {
      method: "POST",
      body: JSON.stringify({ revised_answer: revisedAnswer, reason }),
    }),
    "Correction saved. The draft changed and the earlier version remains in history.",
    { focusQuestion: false }
  );
}

async function skip() {
  const question = state.workspace.next_question;
  await runAction(
    "Holding this question for a later session.",
    () => api("/downstream/workspaces/" + state.workspace.workspace_id + "/skip", {
      method: "POST",
      body: JSON.stringify({ question_id: question.id }),
    }),
    "Question held. Open another saved session after this pass to revisit it."
  );
}

async function resumeSession() {
  const held = state.workspace.skipped.length;
  await runAction(
    held ? "Reopening held questions." : "Opening another saved session.",
    () => api("/downstream/workspaces/" + state.workspace.workspace_id + "/resume", {
      method: "POST",
      body: "{}",
    }),
    held
      ? "Held questions reopened without losing previous answers."
      : "Another session is recorded. The structured context remains bounded."
  );
}

async function feedback(action, reason = "") {
  if (!state.workspace) return;
  await runAction(
    "Saving your presentation preference.",
    () => api("/downstream/workspaces/" + state.workspace.workspace_id + "/feedback", {
      method: "POST",
      body: JSON.stringify({ action, reason }),
    }),
    action === "accept"
      ? "Style accepted and recorded in the adaptation history."
      : "Detail preference changed to concise and is visible below.",
    { focusQuestion: false }
  );
}

async function loadNid() {
  const box = $("#nid-result");
  const button = $("#load-nid");
  button.disabled = true;
  box.innerHTML = "<p>Querying the official USACE service.</p>";
  try {
    const result = await api("/downstream/nid/search?limit=5");
    const records = result.records.map((row) =>
      "<li><b>" + text(row.NAME || "Unnamed record") + "</b>, " +
      text(row.STATE || "state unreported") + " (" + text(row.NIDID || "no id") + ")</li>"
    ).join("");
    box.innerHTML = '<p><span class="live-badge">' + (result.live ? "Live federal response" : "Explicit fallback") +
      '</span></p><p>' + text(result.interpretation) + '</p>' +
      (records ? "<ul>" + records + "</ul>" : "<p>No records represented as current.</p>");
  } catch (error) {
    box.innerHTML = '<p class="field-error">The public service could not be reached. ' + text(error.message) + '</p>';
  } finally {
    button.disabled = false;
  }
}

function initTheme() {
  const button = $("#theme-toggle");
  button.addEventListener("click", () => {
    const dark = document.documentElement.dataset.theme === "dark";
    document.documentElement.dataset.theme = dark ? "" : "dark";
    button.textContent = dark ? "Dark mode" : "Light mode";
    button.setAttribute("aria-pressed", String(!dark));
  });
}

async function runWholeThing() {
  setBusy(true);
  // What this request does, stated up front. Deliberately not a fake progress animation: the run
  // is one server-side call and the page cannot observe it midway, so pretending to narrate live
  // steps would be theatre. This says what was asked for; the timeline underneath says what
  // actually happened, with real timestamps.
  const panel = $("#run-plan");
  if (panel) {
    panel.hidden = false;
    panel.innerHTML =
      "<b>Running one request. It will:</b><ol>" +
      [
        "resolve the dam record",
        "read the 1958 drawing with Gemini",
        "quarantine anything shaped like an instruction",
        "keep only facts it can quote",
        "check the drawing against the registry",
        "draft the sections it has evidence for",
        "refuse the map it cannot justify",
        "schedule its own follow-ups",
      ].map((s) => "<li>" + s + "</li>").join("") +
      "</ol><span class=\"small muted\">Then it stops and asks you the rest.</span>";
  }
  setStatus("Running server-side. Nothing to click.", "neutral");
  try {
    const result = await api("/downstream/demo/run", {method: "POST"});
    const workspace = await api("/downstream/workspaces/" + result.workspace_id);
    render(workspace);
    setStatus(
      "Done in " + Math.round(result.elapsed_ms) + " ms: " +
      result.autonomy_proof.automatic_agent_steps + " steps on its own, " +
      result.scheduled_actions_fired.length + " follow-ups fired, 0 clicks. " +
      "Owner answers were synthetic and the follow-ups ran on a simulated clock. " +
      "The real clock is proven further down.",
      "success",
    );
    if (panel) panel.hidden = true;
    document.querySelector("#autonomy-pane").scrollIntoView({behavior: "smooth", block: "start"});
  } catch (error) {
    setStatus(error.message, "error");
  } finally {
    setBusy(false);
  }
}

let liveProofPoll = null;

async function armLiveProof() {
  if (!state.workspace) {
    setStatus("Open a workspace first, then arm the real-clock reminder.", "error");
    return;
  }
  const button = $("#arm-live-proof");
  const line = $("#live-proof-status");
  button.disabled = true;
  window.clearInterval(liveProofPoll);
  try {
    const armed = await api(
      "/downstream/workspaces/" + state.workspace.workspace_id + "/live-proof",
      {method: "POST"},
    );
    line.className = "small muted armed";
    line.textContent =
      "Armed. Due in " + armed.seconds_until_due +
      " seconds on the real clock. Nothing on this page will run it.";

    // Polling only asks whether the scheduler has been yet. It never causes the work, which is
    // the whole property this card exists to demonstrate.
    const startedAt = Date.now();
    liveProofPoll = window.setInterval(async () => {
      const elapsed = Math.round((Date.now() - startedAt) / 1000);
      try {
        const status = await api("/downstream/live-proof/" + armed.wake_id);
        if (status.fired) {
          window.clearInterval(liveProofPoll);
          line.className = "small fired";
          line.textContent =
            "Fired after " + elapsed + " seconds, executed by Cloud Run revision " +
            (status.revision || "unknown") + " at " +
            new Date(status.fired_at).toLocaleTimeString() +
            ". This page did not run it.";
          // Update the receipt in place, not the whole console. This fires while the user is
          // doing something else -- that is the entire point of it -- so a full re-render would
          // wipe a half-typed correction out from under them at an unpredictable moment.
          const refreshed = await api("/downstream/workspaces/" + armed.workspace_id);
          state.workspace = refreshed;
          renderAutonomy(refreshed);
          showProofRecord(line, armed, status);
          button.disabled = false;
          return;
        }
        line.textContent =
          status.seconds_until_due
            ? "Waiting. Due in " + status.seconds_until_due + " seconds. " + elapsed + "s elapsed."
            : "Due now, waiting for the scheduler's next pass. " + elapsed + "s elapsed.";
      } catch (error) {
        window.clearInterval(liveProofPoll);
        line.className = "small muted";
        line.textContent = error.message;
        button.disabled = false;
      }
    }, 3000);
  } catch (error) {
    line.className = "small muted";
    line.textContent = error.message;
    button.disabled = false;
  }
}

// Rehearsing the demo meant reloading the page to get a clean console, which drops the warmed
// service and costs a cold start on the next run -- the one thing the recording notes say to
// avoid. This clears the workspace in place and leaves the tab warm.
function resetDemo() {
  window.clearInterval(liveProofPoll);
  state.workspace = null;
  state.lastRevised = null;

  const url = new URL(window.location.href);
  url.searchParams.delete("workspace");
  url.hash = "workspace";
  window.history.replaceState({}, "", url);

  $("#console-empty").hidden = false;
  ["#console-shell", "#autonomy-pane", "#workspace-identity"].forEach((selector) => {
    const node = $(selector);
    if (node) node.hidden = true;
  });

  const wrap = $("#autonomy-timeline-wrap");
  if (wrap) {
    wrap.open = false;
    delete wrap.dataset.count;
  }
  $("#autonomy-timeline").innerHTML = "";
  $("#autonomy-highlights").innerHTML = "";
  $("#autonomy-latest").innerHTML = "";
  const plan = $("#run-plan");
  if (plan) plan.hidden = true;

  // The tiles have to go back to zero too. Leaving 15 automatic steps on screen after a clear
  // would be a count that belongs to a run that no longer exists -- the one kind of error this
  // panel exists to make impossible.
  $("#autonomy-grid").innerHTML = [
    "Steps it took on its own", "Facts only the owner could give", "Clicks needed to keep it going",
    "Follow-ups it scheduled for itself",
  ].map((label) => '<div class="profile-item"><small>' + label + "</small><b>0</b></div>").join("");
  $("#autonomy-waiting").textContent = "Start the preset to open a run.";

  const proofLine = $("#live-proof-status");
  proofLine.className = "small muted";
  proofLine.textContent = "Not armed.";
  const record = $("#proof-record");
  if (record) record.remove();
  $("#arm-live-proof").disabled = false;

  updatePersistentControls();
  setStatus("Cleared. The service is still warm, so the next run will not pay a cold start.", "neutral");
}

// The fired line used to be the end of the proof: a sentence to take on trust or not, with
// nothing to click. It now links to the step the scheduler actually wrote into the timeline, and
// the job record sits under it -- wake id, armed, due, fired, revision -- so the claim is
// checkable on the page rather than asserted by it.
function showProofRecord(line, armed, status) {
  const jump = document.createElement("button");
  jump.type = "button";
  jump.className = "proof-jump";
  jump.id = "proof-jump";
  jump.textContent = "See the step it wrote";
  jump.addEventListener("click", () => {
    const wrap = $("#autonomy-timeline-wrap");
    if (wrap && !wrap.open) wrap.open = true;
    const target = [...document.querySelectorAll(
      '#autonomy-timeline .timeline-step[data-step="unattended_review_ran"]'
    )].pop();
    if (!target) return;
    target.scrollIntoView({ behavior: "smooth", block: "center" });
    target.classList.remove("is-flash");
    void target.offsetWidth;
    target.classList.add("is-flash");
  });
  line.append(" ", jump);

  let record = $("#proof-record");
  if (!record) {
    record = document.createElement("dl");
    record.id = "proof-record";
    record.className = "proof-record";
    line.insertAdjacentElement("afterend", record);
  }
  const when = (iso) => (iso ? new Date(iso).toLocaleTimeString() : "\u2014");
  record.innerHTML = [
    ["Wake id", status.wake_id || armed.wake_id],
    ["Armed", when(status.armed_at || armed.armed_at)],
    ["Due", when(status.due_at || armed.due_at)],
    ["Fired", when(status.fired_at)],
    ["Waited", status.waited_seconds != null ? status.waited_seconds + " s" : "\u2014"],
    ["Ran on", status.revision || "unknown"],
  ].map(([k, v]) => "<div><dt>" + text(k) + "</dt><dd>" + text(v) + "</dd></div>").join("");
}

$("#arm-live-proof").addEventListener("click", armLiveProof);
$("#reset-demo").addEventListener("click", resetDemo);
$("#start-demo").addEventListener("click", start);
$("#run-whole-thing").addEventListener("click", runWholeThing);
// The same two actions, offered where a cold visitor actually looks: the console header and the
// empty state itself, rather than only in a panel below the fold.
["#run-top", "#run-empty"].forEach((s) => $(s)?.addEventListener("click", runWholeThing));
$("#start-empty")?.addEventListener("click", start);
$("#load-nid").addEventListener("click", loadNid);
$("#accept-plan").addEventListener("click", () => feedback("accept"));
$("#less-detail").addEventListener("click", () => feedback("not_right", "Too much detail"));
$("#copy-resume").addEventListener("click", async () => {
  if (!state.workspace) return;
  try {
    await navigator.clipboard.writeText(workspaceLink(state.workspace.workspace_id).toString());
    setStatus("Resume link copied.", "success");
  } catch {
    $("#resume-url").focus();
    setStatus("Copy was unavailable. The resume link is focused and ready to copy.", "neutral");
  }
});

initTheme();
const requestedWorkspace = new URLSearchParams(window.location.search).get("workspace");
if (requestedWorkspace) {
  restore(requestedWorkspace);
} else if (state.guided) {
  start();
} else {
  setStatus("");
  // A bare "/" is the front door and opens at the top, unconditionally. The console lives on the
  // home page, so the brand link is often a link to the page you are already on -- and a browser
  // that classifies that as a reload will restore the old scroll position, which reads as "it
  // just refreshed" rather than "it took me home". With no workspace to restore and no anchor to
  // honour, there is nothing to preserve, so restoration is switched off before it can run.
  if (!window.location.hash) {
    if ("scrollRestoration" in window.history) window.history.scrollRestoration = "manual";
    window.scrollTo(0, 0);
  }
}
