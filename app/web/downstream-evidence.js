const $ = (selector) => document.querySelector(selector);

function text(value) {
  const node = document.createElement("span");
  node.textContent = value == null ? "" : String(value);
  return node.innerHTML;
}

async function getJson(path) {
  const response = await fetch(path);
  if (!response.ok) throw new Error(response.status + " " + response.statusText);
  return response.json();
}

function renderProof(proof) {
  $("#proof-score").textContent = proof.passed + "/" + proof.total;
  $("#proof-checks").innerHTML = proof.checks.map((check) =>
    '<li class="' + (check.pass ? "" : "failed") + '"><b>' +
    (check.pass ? "Passed: " : "Failed: ") + text(check.check) + '</b>' +
    (check.detail ? '<span>' + text(check.detail) + '</span>' : "") + '</li>'
  ).join("");
}

function renderConformance(conformance) {
  $("#conformance-grid").innerHTML = conformance.rules.map((rule) =>
    '<article class="evidence-panel"><span class="basis-badge">Rule mapped</span><h3>' +
    text(rule.rule) + '</h3><p>' + text(rule.implementation) + '</p><code>' +
    text(rule.test) + '</code></article>'
  ).join("");
}

function renderDrawing(drawing) {
  const accuracy = drawing.accuracy;
  const passed = accuracy.correct ?? accuracy.passed ?? accuracy.checks_passed ?? 0;
  const total = accuracy.total ?? accuracy.checks_total ?? 5;
  $("#drawing-score").textContent = passed + "/" + total;
  $("#drawing-note").textContent = drawing.note + " Quotes remain attributable to Gemini's recorded transcription.";
}

function renderGemma(gemma) {
  const recall = gemma.measured.recall;
  $("#gemma-score").textContent = recall.found + "/" + recall.expected;
  const leaked = gemma.identifiers_leaked_in_replay || [];
  $("#gemma-note").textContent = leaked.length
    ? leaked.length + " returned identifiers require review."
    : "No returned identifier leaked in the recorded replay.";
}

const ACTOR_LABELS = {
  agent: "Agent",
  human_authority: "Owner authority",
  external_evidence: "External event",
};

function renderAutonomy(run) {
  const proof = run.autonomy_proof;
  const tiles = [
    ["Automatic agent steps", proof.automatic_agent_steps],
    ["Owner authority steps", proof.human_authority_steps],
    ["Continue clicks required", proof.continue_clicks_required],
    ["Durable wakes fired", run.scheduled_actions_fired.length],
    ["Questions the agent raised", run.questions_asked_by_the_agent.length],
    ["Run time", run.elapsed_ms + " ms"],
  ];
  $("#autonomy-tiles").innerHTML = tiles.map(([label, value]) =>
    '<article class="evidence-panel"><h3>' + label + '</h3><div class="evidence-result"><strong>' +
    value + "</strong></div></article>").join("");
  $("#autonomy-waiting").textContent =
    "Trigger: " + proof.trigger.replaceAll("_", " ") + ". Now waiting on " + proof.waiting_on +
    ". Owner answers in this run are synthetic, and the rehearsal clock was simulated so a wake " +
    "due in three days could fire inside one request.";
  $("#autonomy-summary").textContent = "Run timeline, " + proof.timeline.length + " steps";
  $("#autonomy-timeline").innerHTML = proof.timeline.map((step) =>
    '<li><b>' + (ACTOR_LABELS[step.actor] || step.actor) + "</b><span>" + step.detail +
    "</span><small>" + step.step.replaceAll("_", " ") + "</small></li>").join("");
}

async function loadEvidence() {
  try {
    const [proof, conformance, drawing, gemma, run] = await Promise.all([
      getJson("/downstream/proof"),
      getJson("/downstream/conformance"),
      getJson("/downstream/fixtures/drawing"),
      getJson("/downstream/bonus"),
      // Not a fixture: this executes the agent now, and the panel reports what it did.
      fetch("/downstream/demo/run", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: "{}",
      }).then((r) => (r.ok ? r.json() : Promise.reject(new Error("live run unavailable")))),
    ]);
    renderProof(proof);
    renderConformance(conformance);
    renderDrawing(drawing);
    renderGemma(gemma);
    renderAutonomy(run);
    const status = $("#evidence-status");
    status.className = "app-status success";
    status.textContent = "A live agent run plus four public evidence sources loaded. " +
      run.autonomy_proof.automatic_agent_steps + " automatic steps with " +
      run.autonomy_proof.continue_clicks_required + " continue clicks, and " +
      proof.passed + "/" + proof.total + " executable safety checks pass.";
  } catch (error) {
    const status = $("#evidence-status");
    status.className = "app-status error";
    status.textContent = "Evidence could not be loaded: " + error.message;
  }
}

$("#theme-toggle").addEventListener("click", () => {
  const dark = document.documentElement.dataset.theme === "dark";
  document.documentElement.dataset.theme = dark ? "" : "dark";
  $("#theme-toggle").textContent = dark ? "Dark mode" : "Light mode";
  $("#theme-toggle").setAttribute("aria-pressed", String(!dark));
});

loadEvidence();
