"""Generate the Downstream architecture diagram as SVG with explicit coordinates.

Mermaid's auto-layout produced edges that swooped across the whole canvas. Placing every box by
hand costs more to write and is the only way to guarantee a judge can follow it.

Layout rule: no diagonal connectors. A service the agent calls is named inside the step that
calls it, so the right-hand column is an inventory with no arrows crossing the pipeline.
"""
import pathlib

W, H = 1680, 1010
INK, MUTED = "#16222e", "#5d6f80"
BORDER, SOFT = "#c7d3df", "#f4f7fa"
GREEN, GREEN_BG = "#1f6f4a", "#e6f2ec"
AMBER, AMBER_BG = "#9a5b00", "#fdf1de"
RED, RED_BG = "#a8271f", "#fbeae9"
BLUE, BLUE_BG = "#2b5c8a", "#e8f0f8"

out = []
a = out.append


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def box(x, y, w, h, title, sub=None, tag=None, stroke=BORDER, fill="#ffffff", tc=INK, bold=True):
    a(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>')
    cy = y + h / 2
    if sub and tag:
        a(f'<text x="{x + w/2}" y="{cy - 13}" text-anchor="middle" font-size="16" font-weight="650" fill="{tc}">{esc(title)}</text>')
        a(f'<text x="{x + w/2}" y="{cy + 6}" text-anchor="middle" font-size="13" fill="{MUTED}">{esc(sub)}</text>')
        a(f'<text x="{x + w/2}" y="{cy + 25}" text-anchor="middle" font-size="12" font-weight="700" fill="{GREEN}">{esc(tag)}</text>')
    elif sub:
        a(f'<text x="{x + w/2}" y="{cy - 5}" text-anchor="middle" font-size="16" font-weight="{"650" if bold else "500"}" fill="{tc}">{esc(title)}</text>')
        a(f'<text x="{x + w/2}" y="{cy + 15}" text-anchor="middle" font-size="13" fill="{MUTED}">{esc(sub)}</text>')
    else:
        a(f'<text x="{x + w/2}" y="{cy + 6}" text-anchor="middle" font-size="16" font-weight="650" fill="{tc}">{esc(title)}</text>')


def lane(x, y, w, h, label, note=None):
    a(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="14" fill="{SOFT}" stroke="{BORDER}" stroke-width="1.5" stroke-dasharray="7 5"/>')
    a(f'<text x="{x + 18}" y="{y + 27}" font-size="14" font-weight="700" letter-spacing="0.8" fill="{BLUE}">{esc(label.upper())}</text>')
    if note:
        a(f'<text x="{x + w - 18}" y="{y + 27}" text-anchor="end" font-size="13" fill="{MUTED}">{esc(note)}</text>')


def down(x, y1, y2, label=None, lx=None):
    a(f'<path d="M{x},{y1} V{y2}" stroke="{MUTED}" stroke-width="1.8" fill="none" marker-end="url(#ah)"/>')
    if label:
        a(f'<text x="{lx or x + 8}" y="{(y1+y2)/2 + 4}" font-size="12.5" fill="{MUTED}">{esc(label)}</text>')


def right(x1, x2, y, label=None):
    a(f'<path d="M{x1},{y} H{x2}" stroke="{MUTED}" stroke-width="1.8" fill="none" marker-end="url(#ah)"/>')
    if label:
        a(f'<text x="{(x1+x2)/2}" y="{y - 9}" text-anchor="middle" font-size="12.5" fill="{MUTED}">{esc(label)}</text>')


a(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="Segoe UI, Inter, system-ui, sans-serif">')
a(f'<defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
  f'<path d="M0,1 L9,5 L0,9 z" fill="{MUTED}"/></marker></defs>')
a(f'<rect width="{W}" height="{H}" fill="#ffffff"/>')

# Title. The two spans are placed on separate lines: measuring text width in raw SVG is
# guesswork, and the first attempt had them overlapping.
a(f'<text x="50" y="50" font-size="27" font-weight="750" fill="{INK}">Downstream</text>')
a(f'<text x="50" y="76" font-size="16" fill="{MUTED}">How one request becomes a reviewable emergency action plan. Everything runs on Google Cloud in us-central1, except the one box marked external.</text>')

# ---------------------------------------------------------------- triggers
lane(50, 100, 1140, 96, "A run starts from an event, never a button", "0 clicks needed to keep it going")
TW = 356
tx = [72, 72 + TW + 26, 72 + 2 * (TW + 26)]
box(tx[0], 132, TW, 52, "Public console", "no key, no account", stroke=BLUE, fill=BLUE_BG, tc=BLUE)
box(tx[1], 132, TW, 52, "API client", "self-serve key in about a second", stroke=BLUE, fill=BLUE_BG, tc=BLUE)
box(tx[2], 132, TW, 52, "Owner returns to a saved workspace", "days or weeks later", stroke=BLUE, fill=BLUE_BG, tc=BLUE)

# ---------------------------------------------------------------- the run
lane(50, 228, 1140, 476, "Cloud Run  ·  the agent", "FastAPI, Python 3.12")
for x in tx:
    down(x + TW / 2, 184, 222)

PW, PH, GAP = 258, 70, 26
px = [72 + i * (PW + GAP) for i in range(4)]

R1 = 276
box(px[0], R1, PW, PH, "1  Resolve the record", "the console preset is synthetic", "USACE NID  ·  external, live from the API")
box(px[1], R1, PW, PH, "2  Read the 1958 drawing", "a quote kept for every fact", "Vertex AI  ·  Gemini 3.5 Flash, live")
box(px[2], R1, PW, PH, "3  Quarantine gate", "strips instruction-shaped text", stroke=AMBER, fill=AMBER_BG, tc=AMBER)
box(px[3], R1, PW, PH, "4  Quote gate", "a fact must quote its source", stroke=AMBER, fill=AMBER_BG, tc=AMBER)
for i in range(3):
    right(px[i] + PW, px[i + 1] - 4, R1 + PH / 2)

R2 = 388
box(px[0], R2, PW, PH, "5  Sources disagree?", "drawing 31 ft, registry 28 ft")
box(px[1], R2, PW, PH, "6  Mapping gate", "three conditions, fails closed", stroke=AMBER, fill=AMBER_BG, tc=AMBER)
box(px[2], R2, PW, PH, "7  Schedule its follow-ups", "durable records, not browser timers")
box(px[3], R2, PW, PH, "8  Compose the sections", "each one names its evidence")
for i in range(3):
    right(px[i] + PW, px[i + 1] - 4, R2 + PH / 2)
# snake from the end of row one back to the start of row two
a(f'<path d="M{px[3] + PW/2},{R1 + PH} V{R1 + PH + 20} H{px[0] + PW/2} V{R2 - 4}" stroke="{MUTED}" stroke-width="1.8" fill="none" marker-end="url(#ah)"/>')

R3 = 502
box(px[0], R3, PW, PH, "Raises one question", "with both values attached", stroke=AMBER, fill=AMBER_BG, tc=AMBER, bold=False)
box(px[1], R3, PW, PH, "No flood map drawn", "a qualified engineer decides", stroke=RED, fill=RED_BG, tc=RED, bold=False)
box(px[3], R3, PW, PH, "Stops at owner knowledge", "the one input it may not invent",
    stroke=AMBER, fill=AMBER_BG, tc=AMBER, bold=False)
a(f'<text x="{px[2] + PW/2}" y="{R3 + 30}" text-anchor="middle" font-size="13" fill="{MUTED}">An owner answer is pseudonymised</text>')
a(f'<text x="{px[2] + PW/2}" y="{R3 + 49}" text-anchor="middle" font-size="13" fill="{MUTED}">before it reaches a model.</text>')
down(px[0] + PW / 2, R2 + PH, R3 - 4, "yes")
down(px[1] + PW / 2, R2 + PH, R3 - 4, "not proven")
down(px[3] + PW / 2, R2 + PH, R3 - 4)

R4 = 612
box(72, R4, PW * 4 + GAP * 3, 70, "Reviewable draft",
    "every section cites the owner answer or the published requirement it rests on  ·  not approved, certified, or submitted",
    stroke=GREEN, fill=GREEN_BG, tc=GREEN)
down(px[3] + PW / 2, R3 + PH, R4 - 4)

# ---------------------------------------------------------------- services inventory
lane(1214, 228, 416, 476, "Also in the request path")
SX, SW = 1236, 372
box(SX, 276, SW, 62, "Vertex AI", "Gemini 3.5 Flash, live (recording past the cap)", stroke=GREEN, fill=GREEN_BG, tc=GREEN)
box(SX, 352, SW, 62, "Vertex AI", "Gemma 4 reviews name spans (replayed)", stroke=GREEN, fill=GREEN_BG, tc=GREEN)
box(SX, 428, SW, 62, "Secret Manager", "scheduler token, key digests, pepper")
box(SX, 504, SW, 62, "Cloud Trace", "OpenTelemetry spans for every run")
a(f'<rect x="{SX}" y="580" width="{SW}" height="100" rx="10" fill="{AMBER_BG}" stroke="{AMBER}" stroke-width="1.5"/>')
a(f'<text x="{SX + SW/2}" y="614" text-anchor="middle" font-size="16" font-weight="650" fill="{AMBER}">Fail-closed by design</text>')
for i, line in enumerate(["A gate that cannot prove its", "conditions stops, and says who", "decides instead."]):
    a(f'<text x="{SX + SW/2}" y="{638 + i*19}" text-anchor="middle" font-size="13" fill="{MUTED}">{line}</text>')

# ---------------------------------------------------------------- state
lane(50, 736, 1140, 226, "Firestore  ·  state that outlives the browser tab")
FY, FW = 782, 258
fx = [72 + i * (FW + GAP) for i in range(4)]
box(fx[0], FY, FW, 62, "Workspaces", "the draft and its answers")
box(fx[1], FY, FW, 62, "Durable wake ladder", "claim once, retry, dead-letter")
box(fx[2], FY, FW, 62, "Versioned answers", "a correction keeps both")
box(fx[3], FY, FW, 62, "Keys and quotas", "hashed, per-network limits")
box(72, 866, PW * 4 + GAP * 3, 74, "The autonomy receipt is counted from this stored timeline, not asserted",
    "15 agent steps  ·  7 owner-authority steps  ·  0 clicks  ·  every step records which actor performed it",
    stroke=GREEN, fill=GREEN_BG, tc=GREEN)
down(px[0] + PW / 2, R4 + 70, 730, "writes")

# ---------------------------------------------------------------- unattended
lane(1214, 736, 416, 226, "Runs when nobody is watching")
box(SX, 782, SW, 62, "Cloud Scheduler", "polls every minute", stroke=BLUE, fill=BLUE_BG, tc=BLUE)
box(SX, 866, SW, 74, "Unattended review", "is the plan still complete, and still true?", stroke=BLUE, fill=BLUE_BG, tc=BLUE)
a(f'<path d="M{SX},813 H1202 V722 H{fx[1] + FW/2} V{FY - 4}" stroke="{MUTED}" stroke-width="1.8" fill="none" marker-end="url(#ah)"/>')
a(f'<text x="{fx[1] + FW/2 + 14}" y="716" font-size="12.5" fill="{MUTED}">POST /internal/scan-due</text>')
down(SX + SW / 2, 844, 862)

a("</svg>")

p = pathlib.Path(__file__).with_name("architecture.svg")
p.write_text("\n".join(out), encoding="utf-8")
print("wrote", p, len(out), "elements")
