const state = {
  workspace: null,
  guided: new URLSearchParams(window.location.search).get("guided") === "1",
  busy: false,
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
  box.className = "app-status " + tone;
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
      '<p>Five owner gaps and one retrieved-source conflict are structured with provenance. ' +
      'Mapping remains blocked until qualified evidence satisfies its gate.</p>' +
      '<div class="completion-checks"><span>Owner facts structured</span><span>Conflict retained</span><span>Unsafe map withheld</span></div>' +
      '<div class="btn-row">' + action + '<a class="btn" href="/evidence">Open evidence dashboard</a></div>';
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

function renderPlan(workspace) {
  const ledger = new Map(workspace.evidence_ledger.map((row) => [row.section, row]));
  $("#plan-stack").innerHTML = workspace.plan.map((section) => {
    const evidence = ledger.get(section.key)?.evidence || [];
    const evidenceKinds = [...new Set(evidence.map((item) => item.kind.replaceAll("_", " ")))];
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
  return '<details class="answer-history"><summary>View ' + answer.history.length + ' saved version' +
    (answer.history.length === 1 ? "" : "s") + '</summary><ol>' +
    answer.history.map((entry) => '<li><b>Version ' + entry.version + '</b><span>' +
      text(entry.answer) + '</span><small>' + text(entry.reason) + '</small></li>').join("") +
    '</ol></details>';
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
    answer: "Use the county duty desk after hours, not the daytime office line.",
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

  const options = answers.map(([id, answer]) =>
    '<option value="' + id + '">' + text(id.replaceAll("_", " ")) + ", version " + answer.version + '</option>'
  ).join("");
  $("#revision-card").innerHTML =
    '<span class="eyebrow">Correction loop</span><h3>Change an owner fact without erasing history.</h3>' +
    '<label for="revision-question" class="control-kicker">Answer to revise</label>' +
    '<select class="control" id="revision-question">' + options + '</select>' +
    '<div id="revision-history"></div>' +
    '<label for="revision-answer" class="control-kicker">Corrected answer</label>' +
    '<textarea class="control" id="revision-answer" rows="3"></textarea>' +
    '<label for="revision-reason" class="control-kicker">Why it changed</label>' +
    '<input class="control" id="revision-reason" value="Owner correction after review">' +
    '<p class="field-error" id="revision-error"></p>' +
    '<div class="btn-row"><button id="save-revision" data-action type="button">Revise and preserve history</button>' +
    (state.guided ? '<button id="example-revision" data-action type="button">Use correction example</button>' : "") +
    '</div>';

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
  const vocabulary = Object.keys(profile.vocabulary).length
    ? Object.entries(profile.vocabulary).map(([formal, preferred]) => formal + ": " + preferred).join(", ")
    : "No preferences yet";
  const adaptation = workspace.adaptation;
  $("#profile-grid").innerHTML =
    '<div class="profile-item"><small>Reading level</small><b>' + text(profile.reading_level) + '</b></div>' +
    '<div class="profile-item"><small>Detail style</small><b>' + text(profile.detail_preference) + '</b></div>' +
    '<div class="profile-item"><small>Vocabulary</small><b>' + text(vocabulary) + '</b></div>' +
    '<div class="profile-item"><small>Sessions remembered</small><b>' + adaptation.sessions_remembered + '</b></div>' +
    '<div class="profile-item"><small>Feedback events</small><b>' + adaptation.feedback_events + '</b></div>' +
    '<div class="profile-item"><small>Answer revisions</small><b>' + adaptation.answer_revisions + '</b></div>' +
    '<div class="profile-item"><small>Source conflicts surfaced</small><b>' + adaptation.source_conflicts_surfaced + '</b></div>';
  updatePersistentControls();
}

function updatePersistentControls() {
  const enabled = Boolean(state.workspace) && !state.busy;
  $("#accept-plan").disabled = !enabled;
  $("#less-detail").disabled = !enabled;
}

const STEP_LABELS = {
  agent: "Agent",
  human_authority: "Owner authority",
  external_evidence: "External event",
};

function renderAutonomy(workspace) {
  const proof = workspace.autonomy_proof;
  if (!proof) return;
  const tiles = [
    ["Automatic agent steps", proof.automatic_agent_steps],
    ["Owner authority steps", proof.human_authority_steps],
    ["Continue clicks required", proof.continue_clicks_required],
    ["Durable wakes registered", proof.durable_wakes_registered],
  ];
  $("#autonomy-grid").innerHTML = tiles
    .map(([label, value]) =>
      '<div class="profile-item"><small>' + text(label) + "</small><b>" + text(value) + "</b></div>")
    .join("");
  $("#autonomy-waiting").textContent =
    "Trigger: " + proof.trigger.replaceAll("_", " ") + ". Now waiting on " + proof.waiting_on + ".";
  $("#autonomy-timeline").innerHTML = (proof.timeline || [])
    .map((entry) =>
      '<li class="timeline-step ' + entry.actor + '">' +
      '<b>' + text(STEP_LABELS[entry.actor] || entry.actor) + "</b>" +
      "<span>" + text(entry.detail) + "</span>" +
      "<small>" + text(entry.step.replaceAll("_", " ")) + "</small></li>")
    .join("");
}

function render(workspace, options = {}) {
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
  setStatus("Running the full sequence server-side. Nothing to click.", "neutral");
  try {
    const result = await api("/downstream/demo/run", {method: "POST"});
    const workspace = await api("/downstream/workspaces/" + result.workspace_id);
    render(workspace);
    setStatus(
      "Done in " + result.elapsed_ms + " ms. " +
      result.autonomy_proof.automatic_agent_steps + " automatic steps, " +
      result.scheduled_actions_fired.length + " scheduled actions fired, 0 clicks. " +
      "Owner answers were synthetic; the rehearsal clock was simulated.",
      "success",
    );
    document.querySelector("#autonomy-pane").scrollIntoView({behavior: "smooth", block: "center"});
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
          const refreshed = await api("/downstream/workspaces/" + armed.workspace_id);
          render(refreshed);
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

$("#arm-live-proof").addEventListener("click", armLiveProof);
$("#start-demo").addEventListener("click", start);
$("#run-whole-thing").addEventListener("click", runWholeThing);
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
  setStatus("Choose a clean workspace or the guided judge tour to begin.", "neutral");
}
