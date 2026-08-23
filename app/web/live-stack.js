(() => {
  const header = document.querySelector("header.site .bar");
  if (!header || header.querySelector("[data-live-stack]")) return;

  // This widget used to hold a literal list headed "Live request path" that named Gemini and
  // Cloud Trace. Neither was reachable from a request at the time. It now renders /stack, so the
  // badge can only ever say what the running process actually has wired.
  const widget = document.createElement("div");
  widget.className = "live-stack";
  widget.dataset.liveStack = "";
  widget.innerHTML =
    '<button class="live-stack-trigger" type="button" aria-expanded="false" aria-controls="live-stack-panel">' +
    '<span class="live-stack-dot" aria-hidden="true"></span><span>Live stack</span></button>' +
    '<section class="live-stack-panel" id="live-stack-panel" aria-label="Technology used by Downstream">' +
    '<div class="live-stack-heading"><span class="live-stack-dot" aria-hidden="true"></span>' +
    "<div><strong>Running on Google Cloud</strong><small>Reported by this deployment</small></div></div>" +
    '<div id="live-stack-body"><p class="live-stack-note">Loading.</p></div>' +
    '<p class="live-stack-note">Technology used; no endorsement implied.</p></section>';

  const theme = header.querySelector(".theme-toggle");
  const actions = document.createElement("div");
  actions.className = "header-actions";
  header.append(actions);
  actions.append(widget);
  if (theme) actions.append(theme);

  const trigger = widget.querySelector(".live-stack-trigger");
  const close = () => {
    widget.classList.remove("is-open");
    trigger.setAttribute("aria-expanded", "false");
  };
  trigger.addEventListener("click", (event) => {
    event.stopPropagation();
    const open = !widget.classList.contains("is-open");
    close();
    if (open) {
      widget.classList.add("is-open");
      trigger.setAttribute("aria-expanded", "true");
    }
  });
  widget.addEventListener("click", (event) => event.stopPropagation());
  document.addEventListener("click", close);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      close();
      trigger.focus();
    }
  });

  function text(value) {
    const node = document.createElement("span");
    node.textContent = value == null ? "" : String(value);
    return node.innerHTML;
  }

  function group(title, entries) {
    if (!entries.length) return "";
    const items = entries
      .map((entry) => {
        // "in the request path" and "recorded, not called live" are different claims and the
        // panel has to be able to tell a reader which one applies.
        const state = entry.active ? "active" : "inactive";
        const label = entry.active ? "in the request path" : "not in the request path";
        return (
          '<li class="stack-item ' + state + '">' +
          '<span class="stack-name">' + text(entry.service) + "</span>" +
          '<span class="stack-state">' + label + "</span>" +
          '<span class="stack-detail">' + text(entry.detail) + "</span></li>"
        );
      })
      .join("");
    return '<div class="live-stack-group"><b>' + text(title) + "</b><ul>" + items + "</ul></div>";
  }

  fetch("/stack")
    .then((response) => (response.ok ? response.json() : Promise.reject(new Error("unavailable"))))
    .then((stack) => {
      const quotas = stack.quotas || {};
      const limits = Object.entries(quotas)
        .map(([name, value]) => "<li>" + text(name.replaceAll("_", " ")) + ": " + text(value) + "</li>")
        .join("");
      widget.querySelector("#live-stack-body").innerHTML =
        group("Request path", stack.request_path || []) +
        group("Additional Google AI", stack.additional_google_ai || []) +
        (limits
          ? '<div class="live-stack-group"><b>Daily limits</b><ul class="stack-limits">' +
            limits +
            "</ul></div>"
          : "");
    })
    .catch(() => {
      widget.querySelector("#live-stack-body").innerHTML =
        '<p class="live-stack-note">The service could not report its stack.</p>';
    });
})();
