const state = { workspace: null };
const $ = (selector) => document.querySelector(selector);

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `${response.status} ${response.statusText}`);
  }
  return response.json();
}

function text(value) {
  const node = document.createElement("span");
  node.textContent = value == null ? "" : String(value);
  return node.innerHTML;
}

function renderProgress(workspace) {
  const progress = workspace.progress;
  $("#progress-copy").textContent =
    `${progress.answered} answered, ${progress.skipped} held for later, ${progress.total} total.`;
  const labels = [
    "Access",
    "Emergency contact",
    "Downstream knowledge",
    "History",
    "Resources",
    "Source conflict",
  ];
  $("#progress-list").innerHTML = labels
    .map((label, index) => {
      const done = index < progress.answered + progress.skipped;
      return `<li class="${done ? "done" : ""}"><span class="mark">${done ? "OK" : index + 1}</span><span>${label}</span></li>`;
    })
    .join("");

  const meter = workspace.context_meter;
  const pct = Math.min(100, Math.round((meter.structured_context_tokens / meter.bound) * 100));
  $("#context-meter").innerHTML =
    `<b>${meter.structured_context_tokens} / ${meter.bound} tokens</b>` +
    `<div class="meter"><div class="meter-track"><div class="meter-fill" style="width:${pct}%"></div></div>` +
    `<span>${text(meter.method)}</span></div>`;
}

function renderQuestion(workspace) {
  const question = workspace.next_question;
  if (!question) {
    $("#question-card").innerHTML =
      `<span class="eyebrow">Question set complete</span>` +
      `<h3>The first review draft is ready.</h3>` +
      `<p>Five owner gaps and one retrieved-source conflict are structured with provenance. ` +
      `Mapping remains blocked until qualified evidence satisfies its gate.</p>` +
      `<div class="btn-row"><button id="resume-session" type="button">Open another session</button></div>`;
    $("#resume-session").addEventListener("click", resumeSession);
    return;
  }

  const basis = question.basis === "unresolved_source_conflict"
    ? `<span class="basis-badge conflict">Retrieved sources disagree</span>`
    : `<span class="basis-badge">Missing owner fact</span>`;
  $("#question-card").innerHTML =
    `<div class="question-meta"><span>Question ${question.position} of ${question.total}</span>` +
    `<span>For ${text(question.section)}</span></div>${basis}` +
    `<h3>${text(question.text)}</h3>` +
    `<p class="muted small">Why I am asking: ${text(question.why)}</p>` +
    (question.gloss ? `<p class="gloss"><b>Plain meaning:</b> ${text(question.gloss)}</p>` : "") +
    `<label for="owner-answer" class="control-kicker">Your answer</label>` +
    `<textarea class="control" id="owner-answer" rows="4" placeholder="Use the words you would normally use."></textarea>` +
    `<div class="btn-row"><button class="btn-primary" type="button" id="answer-question">Save and continue</button>` +
    `<button type="button" id="unknown-question">I do not know what that means</button>` +
    `<button type="button" id="skip-question">Skip for now</button></div>`;
  $("#answer-question").addEventListener("click", () => answer(false));
  $("#unknown-question").addEventListener("click", () => answer(true));
  $("#skip-question").addEventListener("click", skip);
}

function renderPlan(workspace) {
  const ledger = new Map(workspace.evidence_ledger.map((row) => [row.section, row]));
  $("#plan-stack").innerHTML = workspace.plan
    .map((section) => {
      const evidence = ledger.get(section.key)?.evidence || [];
      const evidenceKinds = [...new Set(evidence.map((item) => item.kind.replaceAll("_", " ")))];
      const evidenceLabel = evidenceKinds.length ? evidenceKinds.join(" + ") : "unresolved gap";
      return `<article class="plan-section"><h4>${text(section.title)}</h4><p>${text(section.text)}</p>` +
        `<div class="section-meta"><span class="section-status ${section.status}">${text(section.status.replaceAll("_", " "))}</span>` +
        `<span class="evidence-chip">Evidence: ${text(evidenceLabel)}</span></div>` +
        (section.source ? `<p><a href="${section.source.url}">${text(section.source.source)}</a></p>` : "") +
        `</article>`;
    })
    .join("");
}

function renderRevision(workspace) {
  const answers = Object.entries(workspace.answers);
  if (!answers.length) {
    $("#revision-card").innerHTML =
      `<span class="eyebrow">Correction loop</span><h3>Your corrections stay attributable.</h3>` +
      `<p class="muted small">After the first answer, revise it here. Downstream keeps both versions and updates the draft.</p>`;
    return;
  }
  const options = answers
    .map(([id, answer]) => `<option value="${id}">${text(id.replaceAll("_", " "))}, version ${answer.version}</option>`)
    .join("");
  $("#revision-card").innerHTML =
    `<span class="eyebrow">Correction loop</span><h3>Change an owner fact without erasing history.</h3>` +
    `<label for="revision-question" class="control-kicker">Answer to revise</label>` +
    `<select class="control" id="revision-question">${options}</select>` +
    `<label for="revision-answer" class="control-kicker">Corrected answer</label>` +
    `<textarea class="control" id="revision-answer" rows="3"></textarea>` +
    `<label for="revision-reason" class="control-kicker">Why it changed</label>` +
    `<input class="control" id="revision-reason" value="Owner correction after review">` +
    `<div class="btn-row"><button id="save-revision" type="button">Revise and preserve history</button></div>`;
  const select = $("#revision-question");
  const fillCurrent = () => {
    $("#revision-answer").value = workspace.answers[select.value].answer;
  };
  select.addEventListener("change", fillCurrent);
  fillCurrent();
  $("#save-revision").addEventListener("click", reviseSelectedAnswer);
}

function renderProfile(workspace) {
  const profile = workspace.profile;
  const vocabulary = Object.keys(profile.vocabulary).length
    ? Object.entries(profile.vocabulary).map(([formal, preferred]) => `${formal}: ${preferred}`).join(", ")
    : "No preferences yet";
  const adaptation = workspace.adaptation;
  $("#profile-grid").innerHTML =
    `<div class="profile-item"><small>Reading level</small><b>${text(profile.reading_level)}</b></div>` +
    `<div class="profile-item"><small>Vocabulary</small><b>${text(vocabulary)}</b></div>` +
    `<div class="profile-item"><small>Sessions remembered</small><b>${adaptation.sessions_remembered}</b></div>` +
    `<div class="profile-item"><small>Answer revisions</small><b>${adaptation.answer_revisions}</b></div>` +
    `<div class="profile-item"><small>Source conflicts surfaced</small><b>${adaptation.source_conflicts_surfaced}</b></div>`;
  $("#accept-plan").disabled = false;
  $("#less-detail").disabled = false;
}

function render(workspace) {
  state.workspace = workspace;
  renderProgress(workspace);
  renderQuestion(workspace);
  renderPlan(workspace);
  renderRevision(workspace);
  renderProfile(workspace);
}

async function start() {
  render(await api("/downstream/workspaces", { method: "POST", body: "{}" }));
}

async function answer(didNotUnderstand) {
  const question = state.workspace.next_question;
  const answerText = $("#owner-answer").value.trim();
  const fallback = didNotUnderstand ? `Please ask that again in plain language. I call it the ${question.term}.` : "";
  if (!answerText && !fallback) {
    $("#owner-answer").focus();
    return;
  }
  render(await api(`/downstream/workspaces/${state.workspace.workspace_id}/answer`, {
    method: "POST",
    body: JSON.stringify({
      question_id: question.id,
      answer: answerText || fallback,
      did_not_understand: didNotUnderstand,
    }),
  }));
}

async function reviseSelectedAnswer() {
  const questionId = $("#revision-question").value;
  const revisedAnswer = $("#revision-answer").value.trim();
  const reason = $("#revision-reason").value.trim();
  if (!revisedAnswer || !reason) return;
  render(await api(
    `/downstream/workspaces/${state.workspace.workspace_id}/answers/${questionId}/revise`,
    {
      method: "POST",
      body: JSON.stringify({ revised_answer: revisedAnswer, reason }),
    },
  ));
}

async function skip() {
  render(await api(`/downstream/workspaces/${state.workspace.workspace_id}/skip`, {
    method: "POST",
    body: JSON.stringify({ question_id: state.workspace.next_question.id }),
  }));
}

async function resumeSession() {
  render(await api(`/downstream/workspaces/${state.workspace.workspace_id}/resume`, {
    method: "POST",
    body: "{}",
  }));
}

async function feedback(action, reason = "") {
  if (!state.workspace) return;
  render(await api(`/downstream/workspaces/${state.workspace.workspace_id}/feedback`, {
    method: "POST",
    body: JSON.stringify({ action, reason }),
  }));
}

async function loadNid() {
  const box = $("#nid-result");
  box.innerHTML = "<p>Querying the official USACE service.</p>";
  try {
    const result = await api("/downstream/nid/search?limit=5");
    const records = result.records.map((row) =>
      `<li><b>${text(row.NAME || "Unnamed record")}</b>, ${text(row.STATE || "state unreported")} (${text(row.NIDID || "no id")})</li>`
    ).join("");
    box.innerHTML = `<p><span class="live-badge">${result.live ? "Live federal response" : "Explicit fallback"}</span></p>` +
      `<p>${text(result.interpretation)}</p>${records ? `<ul>${records}</ul>` : "<p>No records represented as current.</p>"}`;
  } catch (error) {
    box.textContent = error.message;
  }
}

function initTheme() {
  const button = $("#theme-toggle");
  button.addEventListener("click", () => {
    const dark = document.documentElement.dataset.theme === "dark";
    document.documentElement.dataset.theme = dark ? "" : "dark";
    button.textContent = dark ? "Dark mode" : "Light mode";
  });
}

$("#start-demo").addEventListener("click", () => start().catch((error) => alert(error.message)));
$("#load-nid").addEventListener("click", loadNid);
$("#accept-plan").addEventListener("click", () => feedback("accept"));
$("#less-detail").addEventListener("click", () => feedback("not_right", "Too much detail"));
initTheme();
