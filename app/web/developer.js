/* Downstream developer console.
 *
 * The page does three things: mint a key, run any endpoint against the live service, and document
 * the contract. The response is shown four ways on purpose — a formatted summary for reading, raw
 * JSON for copying, the headers so the rate-limit budget is visible, and the equivalent curl so
 * anything done here can be reproduced in a terminal.
 *
 * The key lives in a module-scoped variable and nowhere else. It is never written to
 * localStorage, sessionStorage, or a cookie.
 */
(() => {
  const $ = (s) => document.querySelector(s);
  const BASE = window.location.origin;
  let apiKey = "";
  let lastRaw = "";

  function esc(value) {
    const node = document.createElement("span");
    node.textContent = value == null ? "" : String(value);
    return node.innerHTML;
  }

  /* ---------------------------------------------------------------- endpoints */

  const ENDPOINTS = [
    {
      id: "v1_info",
      method: "GET",
      path: "/v1",
      auth: true,
      summary: "Who am I, what scope do I have, and what are my limits?",
      detail: "The cheapest way to confirm a key works. Returns the tenant the server minted for it, the key id, and the published quotas.",
    },
    {
      id: "create_workspace",
      method: "POST",
      path: "/v1/workspaces",
      auth: true,
      summary: "Open a private workspace from a real public dam record.",
      detail: "Looks the identifier up in the live USACE NID FeatureServer, then runs the autonomous opening sequence. Returns the workspace, the first question the agent decided to ask, and the autonomy receipt. 404 if the identifier is not in the public inventory; 503 if the federal service is unreachable.",
      body: {nid_id: "IA03081"},
      fields: {nid_id: "An exact NIDID. Find one with GET /downstream/nid/search."},
    },
    {
      id: "get_workspace",
      method: "GET",
      path: "/v1/workspaces/{workspace_id}",
      auth: true,
      params: ["workspace_id"],
      summary: "Fetch current state.",
      detail: "Facts, answers with full revision history, held questions, sessions, the adaptation profile, the composed plan, the evidence ledger, the measured context meter, and the autonomy receipt.",
    },
    {
      id: "autonomy",
      method: "GET",
      path: "/v1/workspaces/{workspace_id}/autonomy",
      auth: true,
      params: ["workspace_id"],
      summary: "What the agent did without being asked.",
      detail: "Counted from the stored run timeline rather than described. Every entry names the actor that performed it: agent, human_authority, or external_evidence.",
    },
    {
      id: "answer",
      method: "POST",
      path: "/v1/workspaces/{workspace_id}/answer",
      auth: true,
      params: ["workspace_id"],
      summary: "Record an owner answer to the question the agent asked.",
      detail: "Set did_not_understand to true instead of answering, and the same question is re-asked in plainer language with a gloss. It never fabricates an answer or advances past the gap.",
      body: {question_id: "access_heavy_rain", answer: "The service road washes out at the low crossing.", did_not_understand: false},
      fields: {
        question_id: "Must be a question the agent actually raised.",
        answer: "1 to 1200 characters.",
        did_not_understand: "Optional. Asks for simpler language instead of answering.",
      },
    },
    {
      id: "revise",
      method: "POST",
      path: "/v1/workspaces/{workspace_id}/answers/{question_id}/revise",
      auth: true,
      params: ["workspace_id", "question_id"],
      summary: "Correct an answer, keeping both versions.",
      detail: "Creates a numbered immutable history entry and recomposes the affected plan section. A reason is required: a correction without one is a 422.",
      body: {revised_answer: "Only the low crossing washes out.", reason: "Owner narrowed the location."},
      fields: {revised_answer: "1 to 1200 characters.", reason: "2 to 500 characters. Required."},
    },
    {
      id: "skip",
      method: "POST",
      path: "/v1/workspaces/{workspace_id}/skip",
      auth: true,
      params: ["workspace_id"],
      summary: "Hold a question for later.",
      detail: "The gap stays visible in the draft. The next session reopens it, and so does the scheduled follow-up wake if the workspace goes quiet.",
      body: {question_id: "emergency_manager"},
    },
    {
      id: "feedback",
      method: "POST",
      path: "/v1/workspaces/{workspace_id}/feedback",
      auth: true,
      params: ["workspace_id"],
      summary: "Tell the partner how you want to be worked with.",
      detail: "action is accept, edit, or not_right. A reason mentioning 'too much detail' switches the profile to terse. An edit of the form \"call it X instead of Y\" teaches a vocabulary preference that changes later questions.",
      body: {action: "not_right", reason: "Too much detail", revised_text: ""},
      fields: {action: "accept | edit | not_right", reason: "Required for not_right.", revised_text: "Required for edit."},
    },
    {
      id: "resume",
      method: "POST",
      path: "/v1/workspaces/{workspace_id}/resume",
      auth: true,
      params: ["workspace_id"],
      summary: "Open a new session.",
      detail: "Reopens every held question and records the session. This is the multi-session behaviour the product exists for: state survives across weeks without replaying a transcript.",
    },
    {
      id: "revoke",
      method: "DELETE",
      path: "/v1/key",
      auth: true,
      summary: "Revoke this key immediately.",
      detail: "Takes effect at once. Subsequent calls with the key return 401.",
    },
    {
      id: "demo_run",
      method: "POST",
      path: "/downstream/demo/run",
      auth: false,
      summary: "The whole workflow in one request, no key needed.",
      detail: "Trigger to reviewable draft server-side, including firing the scheduled wakes on a simulated clock. Returns the autonomy receipt, the plan, the evidence ledger, and the measured context. Owner answers are synthetic and the response says so.",
    },
    {
      id: "nid_search",
      method: "GET",
      path: "/downstream/nid/search?limit=5&state=IA",
      auth: false,
      summary: "Find real NID identifiers.",
      detail: "Live query against the official USACE FeatureServer. A null EAP field means unreported in that field, never that no plan exists.",
    },
    {
      id: "stack",
      method: "GET",
      path: "/stack",
      auth: false,
      summary: "Which Google Cloud services this deployment is actually using.",
      detail: "Derived from the running process, so the badge on every page cannot claim a service the deployment does not have.",
    },
    {
      id: "proof",
      method: "GET",
      path: "/downstream/proof",
      auth: false,
      summary: "Executable safety proof.",
      detail: "Runs the safety, evidence, autonomy, context, and redaction checks live and reports pass or fail for each.",
    },
    {
      id: "health",
      method: "GET",
      path: "/health",
      auth: false,
      summary: "Liveness and configuration disclosure.",
      detail: "Reports persistence backend, model execution mode, tracing state, and wake durability.",
    },
  ];

  /* ---------------------------------------------------------------- status */

  function setStatus(node, message, tone) {
    const box = $(node);
    box.className = "developer-status" + (node === "#connection-status" ? " developer-status-compact" : "") + " " + (tone || "neutral");
    box.textContent = message;
  }

  function setActiveKey(value) {
    apiKey = (value || "").trim();
    $("#active-api-key").value = apiKey;
    const has = Boolean(apiKey);
    setStatus("#connection-status", has ? "A key is loaded in this page session." : "No API key is loaded in this browser session.", has ? "success" : "neutral");
    ["#test-key", "#clear-key", "#revoke-key"].forEach((s) => { $(s).disabled = !has; });
  }

  /* ---------------------------------------------------------------- console */

  function current() {
    return ENDPOINTS.find((e) => e.id === $("#endpoint").value) || ENDPOINTS[0];
  }

  function resolvedPath(endpoint) {
    let path = endpoint.path;
    (endpoint.params || []).forEach((name) => {
      const field = document.querySelector(`[data-param="${name}"]`);
      path = path.replace("{" + name + "}", encodeURIComponent((field && field.value.trim()) || "{" + name + "}"));
    });
    return path;
  }

  function curlFor(endpoint) {
    const parts = ["curl -X " + endpoint.method + " \\"];
    if (endpoint.auth) parts.push('  -H "X-API-Key: $DOWNSTREAM_API_KEY" \\');
    const body = $("#request-body").value.trim();
    if (endpoint.body && body) {
      parts.push('  -H "Content-Type: application/json" \\');
      parts.push("  -d '" + body.replace(/\s+/g, " ") + "' \\");
    }
    parts.push('  "' + BASE + resolvedPath(endpoint) + '"');
    return parts.join("\n");
  }

  function renderEndpointPicker() {
    $("#endpoint").innerHTML = ENDPOINTS.map(
      (e) => '<option value="' + e.id + '">' + esc(e.method + "  " + e.path) + (e.auth ? "" : "  (no key)") + "</option>",
    ).join("");
    syncEndpoint();
  }

  function syncEndpoint() {
    const endpoint = current();
    $("#endpoint-help").textContent = endpoint.summary + " " + endpoint.detail;

    $("#path-params").innerHTML = (endpoint.params || [])
      .map((name) =>
        '<label for="param-' + name + '">' + esc(name.replaceAll("_", " ")) + "</label>" +
        '<input class="control mono" id="param-' + name + '" data-param="' + name + '" placeholder="' + esc(name) + '">')
      .join("");

    const hasBody = Boolean(endpoint.body);
    $("#body-row").hidden = !hasBody;
    $("#request-body").value = hasBody ? JSON.stringify(endpoint.body, null, 2) : "";
    $("#curl-output").textContent = curlFor(endpoint);
  }

  function showTab(name) {
    ["formatted", "raw", "headers", "curl"].forEach((key) => {
      const tab = $("#tab-" + key);
      const panel = $("#panel-" + key);
      const active = key === name;
      tab.setAttribute("aria-selected", String(active));
      tab.classList.toggle("is-active", active);
      panel.hidden = !active;
    });
  }

  /* Readable views for the payloads a judge is most likely to look at. Anything without a
     bespoke view falls back to a generic key/value table, so nothing is ever a blank panel. */
  function formatBody(endpointId, body, status) {
    if (body == null) return '<p class="muted small">No body.</p>';
    if (typeof body !== "object") return "<p>" + esc(body) + "</p>";
    if (body.detail && status >= 400) {
      return '<div class="fmt-error"><b>' + esc(status) + "</b><span>" + esc(body.detail) + "</span></div>";
    }

    const blocks = [];
    const tile = (label, value) => '<div class="fmt-tile"><small>' + esc(label) + "</small><b>" + esc(value) + "</b></div>";

    if (body.api_key) {
      blocks.push('<div class="fmt-grid">' + tile("Tenant", body.tenant_id) + tile("Key id", body.key_id) +
        tile("Expires", new Date(body.expires_at).toLocaleString()) + tile("Keys left today", body.keys_remaining_today ?? "—") + "</div>");
    }
    if (body.workspace_id) blocks.push('<div class="fmt-grid">' + tile("Workspace", body.workspace_id) + "</div>");
    if (body.dam) {
      blocks.push("<h4>Dam</h4><div class=\"fmt-grid\">" + tile("Name", body.dam.name) + tile("State", body.dam.state) +
        tile("Hazard", body.dam.hazard_potential) + tile("EAP field", body.dam.eap_status ?? "unreported") +
        tile("Synthetic", String(body.dam.synthetic)) + "</div>");
    }
    if (body.next_question) {
      blocks.push("<h4>The agent is asking</h4><blockquote class=\"fmt-quote\">" + esc(body.next_question.text) +
        '<small>' + esc(body.next_question.id) + " &middot; because: " + esc(body.next_question.why) + "</small></blockquote>");
    }
    if (body.progress) {
      blocks.push('<div class="fmt-grid">' + tile("Answered", body.progress.answered) + tile("Held", body.progress.skipped) +
        tile("Total", body.progress.total) + "</div>");
    }
    const proof = body.autonomy_proof || (body.automatic_agent_steps !== undefined ? body : null);
    if (proof && proof.automatic_agent_steps !== undefined) {
      blocks.push("<h4>Autonomy receipt</h4><div class=\"fmt-grid\">" +
        tile("Steps it took on its own", proof.automatic_agent_steps) +
        tile("Facts only the owner could give", proof.human_authority_steps) +
        tile("Continue clicks", proof.continue_clicks_required) +
        tile("Durable wakes", proof.durable_wakes_registered) + "</div>" +
        '<p class="small muted">Waiting on ' + esc(proof.waiting_on) + ".</p>");
      if (proof.timeline && proof.timeline.length) {
        blocks.push("<details class=\"answer-history\"><summary>Timeline, " + proof.timeline.length + " steps</summary><ol>" +
          proof.timeline.map((s) => "<li><b>" + esc(s.actor.replaceAll("_", " ")) + "</b> <span>" + esc(s.detail) + "</span></li>").join("") +
          "</ol></details>");
      }
    }
    if (body.plan) {
      blocks.push("<h4>Draft sections</h4><ul class=\"fmt-list\">" + body.plan.map((s) =>
        "<li><b>" + esc(s.title) + "</b> <span class=\"fmt-chip\">" + esc(s.status.replaceAll("_", " ")) + "</span><span>" + esc(s.text) + "</span></li>").join("") + "</ul>");
    }
    if (body.context_meter) {
      const m = body.context_meter;
      blocks.push("<h4>Measured context</h4><div class=\"fmt-grid\">" + tile("Structured", m.structured_context_tokens) +
        tile("Naive replay", m.estimated_transcript_replay_tokens) + tile("Budget", m.bound) +
        tile("Within budget", String(m.within_bound)) + "</div>");
    }
    if (body.records) {
      blocks.push("<h4>" + body.records.length + " public records</h4><ul class=\"fmt-list\">" + body.records.map((r) =>
        "<li><b>" + esc(r.NIDID) + "</b> <span>" + esc(r.NAME) + ", " + esc(r.STATE) + "</span></li>").join("") + "</ul>" +
        '<p class="small muted">' + esc(body.interpretation || "") + "</p>");
    }
    if (body.checks) {
      const passed = body.checks.filter((c) => c.pass).length;
      blocks.push("<h4>" + passed + " of " + body.checks.length + " checks passed</h4><ul class=\"fmt-list\">" +
        body.checks.map((c) => '<li class="' + (c.pass ? "ok" : "bad") + '"><b>' + (c.pass ? "PASS" : "FAIL") + "</b><span>" + esc(c.check) + "</span></li>").join("") + "</ul>");
    }
    if (body.request_path) {
      blocks.push("<h4>Request path</h4><ul class=\"fmt-list\">" + body.request_path.map((r) =>
        '<li class="' + (r.active ? "ok" : "") + '"><b>' + (r.active ? "ACTIVE" : "OFF") + "</b><span>" + esc(r.service) + " &mdash; " + esc(r.detail) + "</span></li>").join("") + "</ul>");
    }
    if (body.revoked) blocks.push('<div class="fmt-tile"><small>Revoked</small><b>' + esc(body.key_id) + "</b></div>");

    if (!blocks.length) {
      blocks.push('<div class="fmt-grid">' + Object.entries(body).slice(0, 12)
        .map(([k, v]) => tile(k.replaceAll("_", " "), typeof v === "object" ? JSON.stringify(v).slice(0, 60) : v)).join("") + "</div>");
    }
    return blocks.join("");
  }

  async function send(endpoint, overrides = {}) {
    const path = overrides.path || resolvedPath(endpoint);
    if (path.includes("{")) throw new Error("Fill in the path parameter first.");
    const init = {method: endpoint.method, headers: {}};
    if (endpoint.auth) {
      if (!apiKey) throw new Error("This endpoint needs a key. Create one above, or pick an endpoint marked (no key).");
      init.headers["X-API-Key"] = apiKey;
    }
    const rawBody = overrides.body !== undefined ? JSON.stringify(overrides.body) : ($("#request-body").value.trim() || "");
    if (endpoint.body && rawBody) {
      try {
        JSON.parse(rawBody);
      } catch {
        throw new Error("The request body is not valid JSON.");
      }
      init.headers["Content-Type"] = "application/json";
      init.body = rawBody;
    }
    const started = performance.now();
    const response = await fetch(path, init);
    const elapsed = Math.round(performance.now() - started);
    const text = await response.text();
    let parsed = null;
    try {
      parsed = JSON.parse(text);
    } catch {
      parsed = text;
    }
    return {response, parsed, text, elapsed, path};
  }

  function renderResponse(endpoint, result) {
    const {response, parsed, text, elapsed, path} = result;
    lastRaw = typeof parsed === "object" ? JSON.stringify(parsed, null, 2) : text;
    $("#raw-output").textContent = lastRaw;
    $("#formatted-output").innerHTML = formatBody(endpoint.id, parsed, response.status);
    const headers = [];
    response.headers.forEach((value, name) => headers.push(name + ": " + value));
    $("#headers-output").textContent = headers.sort().join("\n") || "(none exposed to the browser)";
    $("#curl-output").textContent = curlFor(endpoint).replace(resolvedPath(endpoint), path);
    const ok = response.ok;
    $("#response-status").textContent = endpoint.method + " " + path + " → " + response.status + " " + response.statusText;
    $("#response-status").className = "response-status " + (ok ? "ok" : "bad");
    const remaining = response.headers.get("X-RateLimit-Remaining");
    $("#response-timing").textContent = elapsed + " ms" + (remaining ? " · " + remaining + " left today" : "");
  }

  async function sendCurrent() {
    const endpoint = current();
    $("#send-request").disabled = true;
    try {
      renderResponse(endpoint, await send(endpoint));
      showTab("formatted");
    } catch (error) {
      $("#response-status").textContent = error.message;
      $("#response-status").className = "response-status bad";
      $("#formatted-output").innerHTML = '<div class="fmt-error"><b>Not sent</b><span>' + esc(error.message) + "</span></div>";
      showTab("formatted");
    } finally {
      $("#send-request").disabled = false;
    }
  }

  /* One button that exercises the whole contract, so nobody has to assemble eight calls by hand. */
  async function runSequence() {
    if (!apiKey) {
      setStatus("#developer-status", "Create a key first, then run the sequence.", "error");
      return;
    }
    const log = $("#sequence-steps");
    log.innerHTML = "";
    $("#sequence-log").hidden = false;
    $("#run-sequence").disabled = true;

    const step = (label, ok, note) => {
      log.insertAdjacentHTML("beforeend",
        '<li class="' + (ok ? "ok" : "bad") + '"><b>' + (ok ? "OK" : "FAIL") + "</b><span>" + esc(label) + "</span><small>" + esc(note) + "</small></li>");
    };

    try {
      const find = await fetch("/downstream/nid/search?limit=1&state=IA").then((r) => r.json());
      const nid = find.records[0].NIDID;
      step("Found a live public record", true, nid + " — " + find.records[0].NAME);

      let r = await send(ENDPOINTS.find((e) => e.id === "create_workspace"), {path: "/v1/workspaces", body: {nid_id: nid}});
      const ws = r.parsed;
      step("POST /v1/workspaces", r.response.ok, r.response.status + " → " + (ws.workspace_id || ws.detail));
      if (!r.response.ok) throw new Error(ws.detail || "workspace creation failed");
      const id = ws.workspace_id;
      const qid = ws.next_question.id;

      const call = async (label, method, path, body) => {
        const res = await send({method, path, auth: true, body: body || null}, {path, body});
        step(label, res.response.ok, res.response.status + (res.parsed && res.parsed.detail ? " " + res.parsed.detail : ""));
        renderResponse({...ENDPOINTS[0], method, path, auth: true, id: "seq"}, res);
        return res.parsed;
      };

      await call("POST answer", "POST", `/v1/workspaces/${id}/answer`, {question_id: qid, answer: "The service road washes out at the low crossing."});
      const afterSkip = await call("POST skip", "POST", `/v1/workspaces/${id}/skip`, {question_id: "emergency_manager"});
      await call("POST revise", "POST", `/v1/workspaces/${id}/answers/${qid}/revise`, {revised_answer: "Only the low crossing washes out.", reason: "Owner narrowed the location."});
      await call("POST feedback", "POST", `/v1/workspaces/${id}/feedback`, {action: "not_right", reason: "Too much detail"});
      const resumed = await call("POST resume", "POST", `/v1/workspaces/${id}/resume`, undefined);
      const receipt = await call("GET autonomy", "GET", `/v1/workspaces/${id}/autonomy`, undefined);
      const final = await call("GET workspace", "GET", `/v1/workspaces/${id}`, undefined);

      step("Held question reopened on resume", (resumed.sessions.at(-1).reopened_questions || []).includes("emergency_manager"),
        "sessions: " + resumed.sessions.length);
      step("Revision kept both versions", final.answers[qid].version === 2, "version " + final.answers[qid].version + ", history " + final.answers[qid].history.length);
      step("Feedback changed the profile", final.profile.detail_preference === "terse", "detail preference: " + final.profile.detail_preference);
      step("Agent worked more than it asked", receipt.automatic_agent_steps > receipt.human_authority_steps,
        receipt.automatic_agent_steps + " automatic vs " + receipt.human_authority_steps + " authority, " + receipt.continue_clicks_required + " clicks");
      step("No inundation extent produced", final.mapping.may_render_extent === false, final.mapping.status);
      void afterSkip;
      showTab("formatted");
    } catch (error) {
      step("Sequence stopped", false, error.message);
    } finally {
      $("#run-sequence").disabled = false;
    }
  }

  /* ---------------------------------------------------------------- reference */

  function renderReference() {
    $("#endpoint-reference").innerHTML = ENDPOINTS.map((e) => {
      const fields = e.fields
        ? "<dl class=\"field-list\">" + Object.entries(e.fields).map(([k, v]) =>
            "<div><dt><code>" + esc(k) + "</code></dt><dd>" + esc(v) + "</dd></div>").join("") + "</dl>"
        : "";
      const body = e.body
        ? '<pre class="developer-code"><code>' + esc(JSON.stringify(e.body, null, 2)) + "</code></pre>"
        : "";
      return '<article class="endpoint-card">' +
        '<div class="endpoint-head"><span class="verb verb-' + e.method.toLowerCase() + '">' + e.method + "</span>" +
        "<code>" + esc(e.path) + "</code>" +
        '<span class="auth-chip">' + (e.auth ? "X-API-Key" : "no key") + "</span></div>" +
        "<p class=\"endpoint-summary\">" + esc(e.summary) + "</p>" +
        "<p class=\"small muted\">" + esc(e.detail) + "</p>" + fields + body + "</article>";
    }).join("");
  }

  /* ---------------------------------------------------------------- wiring */

  fetch("/developer/config")
    .then((r) => (r.ok ? r.json() : Promise.reject(new Error("unavailable"))))
    .then((config) => {
      const open = config.issuance === "open";
      $("#access-mode").textContent = open
        ? "Open self-service issuance"
        : config.issuance === "invite_only" ? "Invite-only issuance" : "Issuance is disabled";
      $("#key-lifetime").textContent = config.ttl_hours + " hour lifetime";
      $("#invitation-row").hidden = !config.requires_invitation;
      if (config.requires_invitation) $("#invitation-code").required = true;
      $("#key-form").querySelector("button[type=submit]").disabled = config.issuance === "disabled";
      const q = config.quotas || {};
      if (q.key_issuances_per_network_per_day) {
        $("#key-allowance").textContent = q.key_issuances_per_network_per_day + " keys per network per day";
        $("#limit-keys").textContent = q.key_issuances_per_network_per_day;
        $("#limit-calls").textContent = q.api_calls_per_key_per_day.toLocaleString();
        $("#limit-workspaces").textContent = q.public_workspaces_per_network_per_day.toLocaleString();
        $("#limit-model").textContent = q.live_model_calls_per_day;
      }
    })
    .catch(() => setStatus("#developer-status", "Access configuration could not be loaded.", "error"));

  $("#key-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const submit = $("#key-form").querySelector("button[type=submit]");
    submit.disabled = true;
    setStatus("#developer-status", "Creating your key...", "neutral");
    const data = new FormData($("#key-form"));
    const payload = {
      label: String(data.get("label") || "").trim(),
      email: String(data.get("email") || "").trim(),
      organisation: String(data.get("organisation") || "").trim(),
      intended_use: String(data.get("intended_use") || "").trim(),
      acknowledge_terms: data.get("acknowledge_terms") === "on",
    };
    const invite = data.get("invitation_code");
    if (invite) payload.invitation_code = invite;
    try {
      const response = await fetch("/developer/keys", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(body.detail || "The key could not be created.");
      setActiveKey(body.api_key);
      $("#api-key").value = body.api_key;
      $("#key-tenant").textContent = body.tenant_id;
      $("#key-expires").textContent = new Date(body.expires_at).toLocaleString();
      $("#key-remaining").textContent = body.keys_remaining_today ?? "—";
      $("#key-result").hidden = false;
      $("#invitation-code").value = "";
      setStatus("#developer-status", "Key created and loaded into this page. Save it now: it is shown once.", "success");
      $("#api-key").focus();
    } catch (error) {
      setStatus("#developer-status", error.message, "error");
    } finally {
      submit.disabled = false;
    }
  });

  $("#copy-key").addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText($("#api-key").value);
      setStatus("#developer-status", "API key copied.", "success");
    } catch {
      $("#api-key").select();
      setStatus("#developer-status", "Copy was unavailable. The key is selected.", "neutral");
    }
  });

  $("#use-key").addEventListener("click", () => {
    const value = $("#active-api-key").value.trim();
    if (!value) {
      setStatus("#connection-status", "Paste a key first.", "error");
      return;
    }
    setActiveKey(value);
  });

  $("#test-key").addEventListener("click", async () => {
    try {
      const {response, parsed} = await send(ENDPOINTS[0]);
      setStatus("#connection-status", response.ok
        ? "Connected. Tenant " + parsed.tenant + "."
        : "Rejected: " + (parsed.detail || response.status), response.ok ? "success" : "error");
    } catch (error) {
      setStatus("#connection-status", error.message, "error");
    }
  });

  $("#clear-key").addEventListener("click", () => setActiveKey(""));

  $("#revoke-key").addEventListener("click", async () => {
    try {
      const {response, parsed} = await send({method: "DELETE", path: "/v1/key", auth: true});
      if (response.ok) {
        setActiveKey("");
        setStatus("#connection-status", "Key revoked. It will not work again.", "success");
      } else {
        setStatus("#connection-status", parsed.detail || "Revocation failed.", "error");
      }
    } catch (error) {
      setStatus("#connection-status", error.message, "error");
    }
  });

  $("#endpoint").addEventListener("change", syncEndpoint);
  $("#request-body").addEventListener("input", () => { $("#curl-output").textContent = curlFor(current()); });
  $("#path-params").addEventListener("input", () => { $("#curl-output").textContent = curlFor(current()); });
  $("#send-request").addEventListener("click", sendCurrent);
  $("#run-sequence").addEventListener("click", runSequence);
  $("#copy-curl").addEventListener("click", async () => {
    await navigator.clipboard.writeText(curlFor(current())).catch(() => {});
  });
  $("#copy-raw").addEventListener("click", async () => {
    await navigator.clipboard.writeText(lastRaw).catch(() => {});
  });
  ["formatted", "raw", "headers", "curl"].forEach((key) => {
    $("#tab-" + key).addEventListener("click", () => showTab(key));
  });

  $("#theme-toggle").addEventListener("click", () => {
    const dark = document.documentElement.dataset.theme === "dark";
    document.documentElement.dataset.theme = dark ? "light" : "dark";
    $("#theme-toggle").textContent = dark ? "Use dark mode" : "Use light mode";
    $("#theme-toggle").setAttribute("aria-pressed", String(!dark));
  });

  renderEndpointPicker();
  renderReference();
  setActiveKey("");
})();
