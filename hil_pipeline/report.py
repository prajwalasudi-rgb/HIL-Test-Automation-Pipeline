"""Test reports: JUnit XML (for GitLab/GitHub test views) and a standalone HTML page."""
from __future__ import annotations

import base64
import html
import io
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import MaxNLocator  # noqa: E402

# Colours from the dataviz reference palette
SERIES = "#2a78d6"
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
BAND = "#f0efec"
GOOD = "#0ca30c"
CRITICAL = "#d03b3b"


def write_junit(results: list[dict], suite: dict, out_file: Path) -> Path:
    failures = sum(1 for r in results if not r["passed"])
    ts = ET.Element("testsuite", name=suite["suite"], tests=str(len(results)),
                    failures=str(failures), errors="0")
    for r in results:
        case = ET.SubElement(ts, "testcase", classname=f"{suite['ecu']}.{r['type']}",
                             name=r["id"])
        if not r["passed"]:
            f = ET.SubElement(case, "failure", message=r["detail"])
            f.text = r["detail"]
        else:
            ET.SubElement(case, "system-out").text = r["detail"]
    out_file.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(ts).write(out_file, encoding="utf-8", xml_declaration=True)
    return out_file


def _cycle_plot(r: dict) -> str:
    """Inter-frame gap per frame against the allowed band; returns base64 PNG."""
    gaps = r.get("gaps_ms") or []
    nominal, tol = r["nominal_ms"], r["tolerance"]
    fig, ax = plt.subplots(figsize=(6.4, 2.4), dpi=110)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    x = list(range(1, len(gaps) + 1))
    ax.axhspan(nominal * (1 - tol), nominal * (1 + tol), color=BAND, zorder=0)
    ax.axhline(nominal, color=MUTED, linewidth=1, linestyle=(0, (4, 3)), zorder=1)
    ax.plot(x, gaps, color=SERIES, linewidth=2, marker="o", markersize=3.5,
            markeredgecolor=SURFACE, markeredgewidth=1, zorder=2)
    ax.text(1.0, 1.02, f"allowed band {nominal * (1 - tol):.0f}-{nominal * (1 + tol):.0f} ms",
            transform=ax.transAxes, ha="right", va="bottom", fontsize=8, color=INK_2)
    ax.set_xlabel("frame", fontsize=8, color=MUTED)
    ax.set_ylabel("gap to previous frame (ms)", fontsize=8, color=MUTED)
    lo = min([nominal * (1 - tol)] + gaps) * 0.9
    hi = max([nominal * (1 + tol)] + gaps) * 1.1
    ax.set_ylim(lo, hi)
    ax.xaxis.set_major_locator(MaxNLocator(integer=True))
    ax.grid(axis="y", color=GRID, linewidth=0.6)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color("#c3c2b7")
    ax.tick_params(colors=MUTED, labelsize=8, length=0)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=SURFACE)
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def write_html(results: list[dict], suite: dict, out_file: Path) -> Path:
    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    ok = passed == total
    esc = html.escape

    rows = []
    for r in results:
        status = ('<span class="pill pass">&#10003; Pass</span>' if r["passed"]
                  else '<span class="pill fail">&#10007; Fail</span>')
        rows.append(f"<tr><td>{status}</td><td><code>{esc(r['id'])}</code></td>"
                    f"<td>{esc(r['type'].replace('_', ' '))}</td>"
                    f"<td>{esc(r['message'])}</td><td>{esc(r['detail'])}</td></tr>")

    plots = []
    for r in results:
        if r["type"] == "cycle_time" and r.get("gaps_ms"):
            verdict = "Pass" if r["passed"] else "Fail"
            cls = "pass" if r["passed"] else "fail"
            plots.append(
                f'<figure><figcaption><strong>{esc(r["message"])}</strong> cycle time '
                f'<span class="pill {cls}">{verdict}</span><br><span class="sub">'
                f'{esc(r["detail"])}</span></figcaption>'
                f'<img alt="Cycle time of {esc(r["message"])}: {esc(r["detail"])}" '
                f'src="data:image/png;base64,{_cycle_plot(r)}"></figure>')

    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>HIL Test Report</title>
<style>
:root {{ --bg:#f9f9f7; --card:{SURFACE}; --ink:{INK}; --ink2:{INK_2}; --line:{GRID};
        --good:#006300; --bad:{CRITICAL}; }}
@media (prefers-color-scheme: dark) {{
  :root {{ --bg:#0d0d0d; --card:#1a1a19; --ink:#ffffff; --ink2:#c3c2b7; --line:#2c2c2a;
          --good:{GOOD}; --bad:#e66767; }} }}
body {{ margin:0; background:var(--bg); color:var(--ink);
       font:15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif; }}
main {{ max-width:960px; margin:0 auto; padding:24px 16px 48px; }}
h1 {{ font-size:22px; margin:0 0 4px; }} h2 {{ font-size:17px; margin:32px 0 12px; }}
.sub {{ color:var(--ink2); font-size:13px; }}
.hero {{ display:flex; gap:24px; flex-wrap:wrap; background:var(--card);
        border:1px solid var(--line); border-radius:10px; padding:16px 20px; margin-top:16px; }}
.hero .n {{ font-size:28px; font-weight:600; font-variant-numeric:tabular-nums; }}
.pill {{ display:inline-block; padding:1px 8px; border-radius:999px; font-size:12px;
        font-weight:600; border:1px solid currentColor; white-space:nowrap; }}
.pass {{ color:var(--good); }} .fail {{ color:var(--bad); }}
.table-wrap {{ overflow-x:auto; background:var(--card); border:1px solid var(--line);
              border-radius:10px; }}
table {{ border-collapse:collapse; width:100%; font-size:13px; }}
th, td {{ text-align:left; padding:8px 12px; border-bottom:1px solid var(--line);
         vertical-align:top; }}
th {{ color:var(--ink2); font-weight:600; }}
figure {{ margin:0 0 16px; background:{SURFACE}; color:{INK}; border:1px solid var(--line);
         border-radius:10px; padding:12px; }}
figure .sub {{ color:{INK_2}; }}
figure img {{ width:100%; height:auto; display:block; margin-top:8px; }}
</style></head><body><main>
<h1>HIL Test Report &middot; {esc(suite['ecu'])} v{esc(suite['version'])}</h1>
<div class="sub">Suite <code>{esc(suite['suite'])}</code> &middot; generated from
<code>{esc(suite['dbc'])}</code> &middot; {time.strftime('%Y-%m-%d %H:%M')}</div>
<div class="hero">
  <div><div class="sub">Result</div><div class="n {'pass' if ok else 'fail'}">
    {'&#10003; PASSED' if ok else '&#10007; FAILED'}</div></div>
  <div><div class="sub">Tests passed</div><div class="n">{passed} / {total}</div></div>
  <div><div class="sub">Recording time</div><div class="n">{suite['duration_s']:g} s</div></div>
</div>
<h2>Results</h2>
<div class="table-wrap"><table>
<thead><tr><th>Status</th><th>Test</th><th>Type</th><th>Message</th><th>Detail</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div>
<h2>Cycle times</h2>
<p class="sub">Each point is the time since the previous frame of that message. The shaded
band is the allowed range; the dashed line is the nominal cycle time.</p>
{''.join(plots)}
</main></body></html>"""
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(page, encoding="utf-8")
    return out_file
