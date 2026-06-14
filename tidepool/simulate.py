#!/usr/bin/env python3
"""
Repo tide-pool ecosystem.

Each public repo is a jellyfish-like creature. Star count sets its base size,
recent activity sets its glow, and a Lotka-Volterra predator-prey simulation
makes the whole scene breathe day to day -- predators (most-starred repos) swell
while grazers (newer/smaller repos) thin out, then the wave reverses.

Pure standard library. No API keys required (uses GITHUB_TOKEN when present only
to lift the rate limit). Output is a single committed, self-animating SVG, so it
renders straight through GitHub's image proxy -- same trick as the snake graph.
"""

import json
import math
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

OWNER = "rohan1402"
PROFILE_REPO = "rohan1402"          # the "reef" -- shown as the central home node
MAX_CREATURES = 7                   # keep the scene readable

ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = ROOT / "tidepool" / "state.json"
OUT_PATH = ROOT / "dist" / "tidepool.svg"

W, H = 680, 440

# Slots the creatures settle into, biggest first. Kept clear of the legend
# (top-left) and the tick counter (top-right), and away from the reef centre.
SLOTS = [
    (168, 168), (500, 150), (566, 296),
    (120, 300), (430, 344), (608, 214), (296, 350),
]
REEF = (332, 244)

# Fallback creatures if the API is unreachable, so the scene never breaks.
FALLBACK = [
    {"name": "patchwork", "stars": 0, "days": 20},
    {"name": "agentically", "stars": 0, "days": 5},
    {"name": "llm-playground", "stars": 0, "days": 12},
    {"name": "f1-race-simulator", "stars": 0, "days": 30},
]


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


# --------------------------------------------------------------------------- #
# Data
# --------------------------------------------------------------------------- #
def fetch_repos():
    url = f"https://api.github.com/users/{OWNER}/repos?per_page=100&type=owner&sort=pushed"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "tidepool-ecosystem",
    }
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.load(resp)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        print(f"warning: repo fetch failed ({e}); using fallback", file=sys.stderr)
        return FALLBACK

    now = datetime.now(timezone.utc)
    repos = []
    for r in data:
        if r.get("fork") or r.get("archived"):
            continue
        if r.get("name") == PROFILE_REPO:
            continue
        pushed = r.get("pushed_at")
        try:
            dt = datetime.strptime(pushed, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            days = max(0, (now - dt).days)
        except (TypeError, ValueError):
            days = 999
        repos.append({
            "name": r["name"],
            "stars": int(r.get("stargazers_count", 0)),
            "days": days,
        })
    if not repos:
        return FALLBACK
    repos.sort(key=lambda r: (r["stars"], -r["days"]), reverse=True)
    return repos[:MAX_CREATURES]


def load_state():
    try:
        return json.loads(STATE_PATH.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {"tick": 0, "prey": 1.0, "pred": 0.78}


def save_state(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2) + "\n")


def step_lotka_volterra(state):
    """Discrete predator-prey step, sub-sampled for a smooth, bounded oscillation."""
    alpha, beta, gamma, delta = 0.66, 0.44, 0.55, 0.38
    prey, pred = state.get("prey", 1.0), state.get("pred", 0.78)
    for _ in range(6):
        dt = 0.02
        dprey = alpha * prey - beta * prey * pred
        dpred = delta * prey * pred - gamma * pred
        prey = clamp(prey + dt * dprey, 0.28, 2.6)
        pred = clamp(pred + dt * dpred, 0.28, 2.6)
    state["prey"], state["pred"] = prey, pred
    return prey, pred


def pop_mult(pop):
    """Map a population level (~0.3..2.6) to a size multiplier (~0.62..1.14)."""
    t = (clamp(pop, 0.3, 2.3) - 0.3) / 2.0
    return 0.62 + 0.52 * t


# --------------------------------------------------------------------------- #
# Palettes
# --------------------------------------------------------------------------- #
PREDATOR_PALETTES = [
    {"body": "#D85A30", "mid": "#e8703f", "dark": "#b8451f", "eye": "#3a140a",
     "name": "#ffd9c7", "sub": "#f0a987"},
    {"body": "#EF9F27", "mid": "#f6b449", "dark": "#b9760f", "eye": "#3a2606",
     "name": "#ffe6bd", "sub": "#e6bc73"},
]
GRAZER_PALETTES = [
    {"body": "#1D9E75", "mid": "#33b88c", "dark": "#0e6e51", "eye": "#06301f",
     "name": "#bff0dc", "sub": "#73c9a5"},
    {"body": "#639922", "mid": "#7bb336", "dark": "#3b6d11", "eye": "#1a3404",
     "name": "#d8eeb0", "sub": "#9ec45a"},
]


def role_label(role, rank):
    if role == "predator":
        return "apex predator" if rank == 0 else "predator"
    return "grazer"


# --------------------------------------------------------------------------- #
# SVG
# --------------------------------------------------------------------------- #
def jellyfish(cx, cy, r, pal, idx, active):
    n = max(3, round(r / 10))
    tentacles = []
    for k in range(n):
        fx = -0.72 * r + (1.44 * r) * (k / max(1, n - 1))
        tip = fx + (3 if k % 2 else -3)
        sw = max(2.4, r * 0.09)
        tentacles.append(
            f'<path d="M{fx:.1f},{r*0.16:.1f} Q{fx-4:.1f},{r*0.72:.1f} {tip:.1f},{r*1.22:.1f}" '
            f'stroke="{pal["dark"]}" stroke-width="{sw:.1f}" fill="none" stroke-linecap="round"/>'
        )
    bob_dur = 6 + (idx % 4) * 1.3
    sway_dur = 4.4 + (idx % 3) * 0.9
    dx = 6 + (idx % 3) * 2
    glow = ""
    if active:
        glow = (
            f'<circle cx="0" cy="0" r="{r*1.18:.1f}" fill="{pal["body"]}" opacity="0.16">'
            f'<animate attributeName="r" values="{r*1.05:.1f};{r*1.32:.1f};{r*1.05:.1f}" '
            f'dur="3.6s" repeatCount="indefinite"/>'
            f'<animate attributeName="opacity" values="0.18;0.05;0.18" dur="3.6s" repeatCount="indefinite"/>'
            f'</circle>'
        )
    return (
        f'<g transform="translate({cx:.0f},{cy:.0f})">'
        f'<g><animateTransform attributeName="transform" type="translate" '
        f'values="0,0; {dx},-8; 0,0" dur="{bob_dur:.1f}s" repeatCount="indefinite"/>'
        f'{glow}'
        f'<g><animateTransform attributeName="transform" type="rotate" '
        f'values="-3.5 0 0; 3.5 0 0; -3.5 0 0" dur="{sway_dur:.1f}s" repeatCount="indefinite"/>'
        f'{"".join(tentacles)}</g>'
        f'<ellipse cx="0" cy="0" rx="{r:.1f}" ry="{r*0.85:.1f}" fill="{pal["body"]}"/>'
        f'<ellipse cx="0" cy="{-r*0.13:.1f}" rx="{r:.1f}" ry="{r*0.62:.1f}" fill="{pal["mid"]}"/>'
        f'<circle cx="{-r*0.31:.1f}" cy="{-r*0.08:.1f}" r="{max(2.6,r*0.11):.1f}" fill="{pal["eye"]}"/>'
        f'<circle cx="{r*0.31:.1f}" cy="{-r*0.08:.1f}" r="{max(2.6,r*0.11):.1f}" fill="{pal["eye"]}"/>'
        f'<circle cx="{-r*0.27:.1f}" cy="{-r*0.13:.1f}" r="1.5" fill="#ffffff"/>'
        f'<circle cx="{r*0.35:.1f}" cy="{-r*0.13:.1f}" r="1.5" fill="#ffffff"/>'
        f'</g></g>'
    )


def label(cx, cy, r, name, stars, sub, pal):
    y = cy + r + 22
    star_txt = f"★ {stars} · {sub}" if stars else f"new · {sub}"
    return (
        f'<text x="{cx:.0f}" y="{y:.0f}" text-anchor="middle" '
        f'font-family="system-ui,sans-serif" font-size="13" font-weight="500" '
        f'fill="{pal["name"]}">{name}</text>'
        f'<text x="{cx:.0f}" y="{y+15:.0f}" text-anchor="middle" '
        f'font-family="system-ui,sans-serif" font-size="11" fill="{pal["sub"]}">{star_txt}</text>'
    )


def reef(cx, cy):
    return (
        f'<g transform="translate({cx},{cy})">'
        f'<g><animateTransform attributeName="transform" type="translate" '
        f'values="0,0; 0,-10; 0,0" dur="5s" repeatCount="indefinite"/>'
        f'<circle cx="0" cy="0" r="24" fill="#7F77DD" opacity="0.25">'
        f'<animate attributeName="r" values="22;31;22" dur="3.5s" repeatCount="indefinite"/>'
        f'<animate attributeName="opacity" values="0.28;0.08;0.28" dur="3.5s" repeatCount="indefinite"/>'
        f'</circle>'
        f'<circle cx="0" cy="0" r="17" fill="#8e87e6"/>'
        f'<circle cx="0" cy="-3" r="13" fill="#a9a3ee"/>'
        f'<circle cx="-5" cy="-1" r="2.6" fill="#2a2560"/>'
        f'<circle cx="5" cy="-1" r="2.6" fill="#2a2560"/>'
        f'</g></g>'
        f'<text x="{cx}" y="{cy+42}" text-anchor="middle" font-family="system-ui,sans-serif" '
        f'font-size="12" font-weight="500" fill="#d8d4fb">{PROFILE_REPO}</text>'
        f'<text x="{cx}" y="{cy+56}" text-anchor="middle" font-family="system-ui,sans-serif" '
        f'font-size="10.5" fill="#b0a9ee">the reef · home</text>'
    )


def render(creatures, tick):
    parts = []
    parts.append(
        f'<svg width="100%" viewBox="0 0 {W} {H}" role="img" xmlns="http://www.w3.org/2000/svg">'
        f'<title>Repo tide-pool ecosystem</title>'
        f'<desc>Each creature is one of {OWNER}\'s repositories, sized by stars, drifting in a '
        f'predator-prey simulation that re-runs daily.</desc>'
    )
    # water
    parts.append(f'<rect x="0" y="0" width="{W}" height="{H}" fill="#07232f"/>')
    parts.append(f'<rect x="0" y="0" width="{W}" height="150" fill="#0c3243"/>')
    parts.append(f'<rect x="0" y="150" width="{W}" height="140" fill="#0a2c3b"/>')
    parts.append(f'<rect x="0" y="290" width="{W}" height="150" fill="#072430"/>')
    # light shafts
    parts.append('<polygon points="120,0 160,0 90,440 30,440" fill="#ffffff" opacity="0.04">'
                 '<animate attributeName="opacity" values="0.02;0.07;0.02" dur="7s" repeatCount="indefinite"/></polygon>')
    parts.append('<polygon points="430,0 470,0 520,440 450,440" fill="#ffffff" opacity="0.04">'
                 '<animate attributeName="opacity" values="0.06;0.02;0.06" dur="9s" repeatCount="indefinite"/></polygon>')
    # floor
    parts.append('<path d="M0,420 Q120,388 260,408 T520,402 T680,414 L680,440 L0,440 Z" fill="#06202b"/>')
    parts.append('<ellipse cx="180" cy="424" rx="26" ry="8" fill="#0a2e3c"/>')
    parts.append('<ellipse cx="470" cy="428" rx="34" ry="9" fill="#0a2e3c"/>')
    parts.append('<ellipse cx="610" cy="422" rx="20" ry="6" fill="#0a2e3c"/>')
    # rising bubbles
    bubbles = [(250, 9, 0), (255, 11, 2), (560, 10, 1), (100, 12, 3), (390, 10.5, 1.5)]
    parts.append('<g>')
    for bx, dur, beg in bubbles:
        parts.append(
            f'<circle cx="{bx}" cy="392" r="2.2" fill="#bfeaff" opacity="0.5">'
            f'<animate attributeName="cy" values="396;-10" dur="{dur}s" begin="{beg}s" repeatCount="indefinite"/>'
            f'<animate attributeName="opacity" values="0;0.6;0" dur="{dur}s" begin="{beg}s" repeatCount="indefinite"/>'
            f'</circle>'
        )
    parts.append('</g>')
    # plankton
    parts.append('<g opacity="0.7">'
                 '<circle cx="380" cy="120" r="3" fill="#7fe9c8"><animate attributeName="cx" values="380;395;380" dur="8s" repeatCount="indefinite"/></circle>'
                 '<circle cx="300" cy="330" r="2.5" fill="#7fe9c8"><animate attributeName="cx" values="300;288;300" dur="7s" repeatCount="indefinite"/></circle>'
                 '<circle cx="600" cy="180" r="2.5" fill="#7fe9c8"><animate attributeName="cy" values="180;168;180" dur="6s" repeatCount="indefinite"/></circle>'
                 '<circle cx="60" cy="200" r="2" fill="#7fe9c8"><animate attributeName="cy" values="200;212;200" dur="9s" repeatCount="indefinite"/></circle>'
                 '</g>')

    # reef core
    parts.append(reef(*REEF))

    # creatures
    for c in creatures:
        parts.append(jellyfish(c["x"], c["y"], c["r"], c["pal"], c["idx"], c["active"]))
    for c in creatures:
        parts.append(label(c["x"], c["y"], c["r"], c["name"], c["stars"], c["sub"], c["pal"]))

    # legend
    parts.append(
        '<rect x="18" y="18" width="232" height="58" rx="10" fill="#04161e" opacity="0.78"/>'
        '<circle cx="36" cy="38" r="5" fill="#D85A30"/>'
        '<text x="48" y="42" font-family="system-ui,sans-serif" font-size="11.5" fill="#cfe9f2">warm = predator (most-starred)</text>'
        '<circle cx="36" cy="58" r="5" fill="#1D9E75"/>'
        '<text x="48" y="62" font-family="system-ui,sans-serif" font-size="11.5" fill="#cfe9f2">cool = grazer (newer / smaller)</text>'
    )
    parts.append(
        f'<text x="662" y="34" text-anchor="end" font-family="system-ui,sans-serif" '
        f'font-size="11" fill="#5d8497">tick {tick:,} · re-simulated daily</text>'
    )
    parts.append('</svg>')
    return "".join(parts)


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main():
    repos = fetch_repos()
    state = load_state()
    state["tick"] = state.get("tick", 0) + 1
    prey, pred = step_lotka_volterra(state)

    max_stars = max(1, max(r["stars"] for r in repos))
    # Top ~40% by stars are predators (at least one), the rest are grazers.
    n_pred = max(1, round(len(repos) * 0.4))

    creatures = []
    for rank, r in enumerate(repos):
        is_pred = rank < n_pred
        role = "predator" if is_pred else "grazer"
        pals = PREDATOR_PALETTES if is_pred else GRAZER_PALETTES
        pal = pals[rank % len(pals)]
        base = 16 + 30 * math.sqrt(r["stars"] / max_stars)
        radius = clamp(base * pop_mult(pred if is_pred else prey), 14, 48)
        creatures.append({
            "name": r["name"],
            "stars": r["stars"],
            "sub": role_label(role, rank),
            "r": radius,
            "pal": pal,
            "active": r["days"] <= 30,
            "idx": rank,
        })

    # Place biggest first into the slots, with a small daily drift.
    creatures.sort(key=lambda c: c["r"], reverse=True)
    for i, c in enumerate(creatures):
        sx, sy = SLOTS[i % len(SLOTS)]
        c["x"] = clamp(sx + 8 * math.sin(state["tick"] * 0.3 + i), 70, W - 70)
        c["y"] = clamp(sy + 6 * math.cos(state["tick"] * 0.21 + i), 120, 350)

    svg = render(creatures, state["tick"])
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(svg)
    save_state(state)

    print(f"tick {state['tick']}: prey={prey:.2f} pred={pred:.2f} "
          f"creatures={len(creatures)} -> {OUT_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
