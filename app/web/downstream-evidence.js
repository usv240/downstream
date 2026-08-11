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

async function loadEvidence() {
  try {
    const [proof, conformance, drawing, gemma] = await Promise.all([
      getJson("/downstream/proof"),
      getJson("/downstream/conformance"),
      getJson("/downstream/fixtures/drawing"),
      getJson("/downstream/bonus"),
    ]);
    renderProof(proof);
    renderConformance(conformance);
    renderDrawing(drawing);
    renderGemma(gemma);
    const status = $("#evidence-status");
    status.className = "app-status success";
    status.textContent = "All four public evidence sources loaded. " + proof.passed + "/" + proof.total + " executable safety checks pass.";
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
