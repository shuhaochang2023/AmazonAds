#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════════╗
║  Amazon Advertising Dashboard Generator                                  ║
║  ─────────────────────────────────────────                               ║
║  Reusable template for all clients.                                      ║
║  To use for a new client: update the ── CLIENT CONFIG ── block below.   ║
╚══════════════════════════════════════════════════════════════════════════╝

File layout (per client folder):
  Products.csv              — upload once; defines Parent/Child mapping
  HistoricalAsinDateSales.csv — ScaleInsight weekly export (any date range)
  SB_Attribution.csv        — optional; Ads Console SB campaign report
  generate_report.py        — this script
  output/                   — generated HTML files go here
"""

from __future__ import annotations
import csv, json, re, os
from datetime import datetime, date
from collections import defaultdict
from pathlib import Path

# ═══════════════════════════════════════════════════════════════════════════
# ── CLIENT CONFIG  (edit this block for each client / period) ──────────────
# ═══════════════════════════════════════════════════════════════════════════

CLIENT_NAME   = "DAIKEN"
MARKET        = "US"
CURRENCY      = "$"           # "$" | "£" | "€" | "A$"
LOCALE        = "en-US"       # "en-US" | "en-GB" | "de-DE"
TACOS_TARGET  = 70            # % threshold for TACOS classification
REPORT_PERIOD = "Feb–Mar 2026"

# Week definitions — add/remove rows to cover any number of weeks
WEEK_RANGES: dict[str, tuple[date, date]] = {
    "W1": (date(2026, 2,  1), date(2026, 2,  7)),
    "W2": (date(2026, 2,  8), date(2026, 2, 14)),
    "W3": (date(2026, 2, 15), date(2026, 2, 21)),
    "W4": (date(2026, 2, 22), date(2026, 2, 28)),
    "W5": (date(2026, 3,  1), date(2026, 3,  7)),
}
W_LABELS: dict[str, str] = {
    "W1": "Feb 1–7", "W2": "Feb 8–14", "W3": "Feb 15–21",
    "W4": "Feb 22–28", "W5": "Mar 1–7",
}

# ── File paths ────────────────────────────────────────────────────────────
INPUT_DIR    = Path("/Users/koda/amazon-autopilot/clients/daiken/input")
SOURCE_HTML  = INPUT_DIR / "DAIKEN_Dashboard_Feb2026.html"  # dark-theme base
PRODUCTS_CSV = INPUT_DIR / "Products.csv"
SALES_CSV    = INPUT_DIR / "HistoricalAsinDateSales.csv"
SB_CSV       = INPUT_DIR / "SB_report.csv"
OUTPUT_DIR   = Path("/Users/koda/amazon-autopilot/output/daiken")
OUTPUT_HTML  = OUTPUT_DIR / f"{CLIENT_NAME}_{MARKET}_{REPORT_PERIOD.replace(' ','_').replace('–','-')}.html"

# ── Frozen weeks (W1-W4 = preserved from SOURCE_HTML, NOT recomputed from CSV) ──
# Preserves the original SP/SD/SB breakdown that's verified in the base HTML.
# Weekly workflow: add new week to WEEK_RANGES + W_LABELS above; leave FROZEN_WEEKS unchanged.
FROZEN_WEEKS = ["W1", "W2", "W3", "W4"]

# ── Frozen weeks (W1-W4 = preserved from SOURCE_HTML, not recomputed) ────────
# These weeks keep their original SP/SD/SB breakdown from the base HTML.
# To add a new week: append to WEEK_RANGES + W_LABELS above. Do NOT add it here.
# Next week workflow: add W6 to WEEK_RANGES, download new CSVs, run script.
FROZEN_WEEKS = ["W1", "W2", "W3", "W4"]

# ── Parent visual config (DAIKEN US — update for other clients) ───────────
PARENT_COLORS: dict[str, str] = {
    "B09Y8VBQTV": "#3b82f6",   # Maca
    "B0DYHLCY51": "#a855f7",   # Fish Oil
    "B0DY7H26GN": "#f59e0b",   # Multivitamin
    "B0DTV2XP8T": "#22c55e",   # Nattokinase
    "B0FF4WBTWX": "#ef4444",   # Bitter Melon
    "B0FKBLZB11": "#06b6d4",   # Lutein
    "B0G7SGXFC1": "#f97316",   # Kids Fish Oil
}
PARENT_SHORTS: dict[str, str] = {
    "B09Y8VBQTV": "Maca Powder",
    "B0DYHLCY51": "Fish Oil",
    "B0DY7H26GN": "Multivitamin",
    "B0DTV2XP8T": "Nattokinase",
    "B0FF4WBTWX": "Bitter Melon",
    "B0FKBLZB11": "Lutein",
    "B0G7SGXFC1": "Kids Fish Oil",
}
# Traditional Chinese display names (optional — leave empty string to use English)
ZH_PARENTS: dict[str, str] = {
    "B09Y8VBQTV": "瑪卡粉",
    "B0DYHLCY51": "成人頂級魚油",
    "B0DY7H26GN": "綜合維生素",
    "B0DTV2XP8T": "納豆激酶",
    "B0FF4WBTWX": "苦瓜酵素",
    "B0FKBLZB11": "葉黃素",
    "B0G7SGXFC1": "兒童魚油軟糖",
}
ZH_CHILDREN: dict[str, str] = {
    "B09Y8VBQTV": "瑪卡粉 · 22包",
    "B0DTT8T7X1": "成人頂級魚油 · 60粒×2",
    "B0DTTHJCRL": "成人頂級魚油 · 60粒",
    "B0DTTT9WTN": "綜合維生素 · 60粒×2",
    "B0DTTVGD2F": "綜合維生素 · 60粒",
    "B0DTYCNVQV": "納豆激酶 · 60粒",
    "B0DTYLYN6B": "納豆激酶 · 60粒×2",
    "B0DV3SJ8LK": "苦瓜酵素 · 60粒×2",
    "B0DV3VX26C": "苦瓜酵素 · 60粒",
    "B0FH6BX4GQ": "葉黃素 · 30粒",
    "B0FH6DDW63": "葉黃素 · 30粒×2",
    "B0G7K1VC4G": "兒童魚油軟糖 · 30粒×2",
    "B0G7K4CHWG": "兒童魚油軟糖 · 30粒",
}

# ═══════════════════════════════════════════════════════════════════════════
# ── DATA PROCESSING ────────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════

WEEKS = list(WEEK_RANGES.keys())

def _pf(v: str) -> float:
    try: return float(str(v).strip().replace("%", "").replace(",", ""))
    except: return 0.0

def _parse_date(s: str) -> date | None:
    for fmt in ("%d-%b-%y", "%Y-%m-%d", "%m/%d/%Y"):
        try: return datetime.strptime(s.strip(), fmt).date()
        except: pass
    return None

def _get_week(d: date) -> str | None:
    for wk, (start, end) in WEEK_RANGES.items():
        if start <= d <= end: return wk
    return None

# ── Load Products.csv → parent/child mapping ─────────────────────────────
def load_products(path: Path) -> tuple[dict, dict]:
    child_to_parent: dict[str, str] = {}
    asin_to_name: dict[str, str]    = {}
    with open(path, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            a = r["ASIN"].strip()
            child_to_parent[a] = r["Parent ASIN"].strip()
            asin_to_name[a]    = r["Title"].strip()
    return child_to_parent, asin_to_name

# ── Load HistoricalAsinDateSales CSV ─────────────────────────────────────
def load_sales(path: Path) -> dict:
    weekly: dict = defaultdict(lambda: defaultdict(
        lambda: {"sales": 0.0, "spend": 0.0, "units": 0, "organic": 0,
                 "ppc": 0, "profits": 0.0}))
    with open(path, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            d  = _parse_date(r.get("Date", ""))
            wk = _get_week(d) if d else None
            if not wk: continue
            a = r.get("ASIN", "").strip()
            if not a: continue
            wd = weekly[a][wk]
            wd["sales"]   += _pf(r.get("Sales",           0))
            wd["spend"]   += _pf(r.get("PPC Cost",         0))
            wd["units"]   += int(_pf(r.get("Units",        0)))
            wd["organic"] += int(_pf(r.get("Organic Units",0)))
            wd["ppc"]     += int(_pf(r.get("PPC Orders",   0)))
            wd["profits"] += _pf(r.get("Profits",          0))
    return weekly

# ── Load SB Attributed Purchases report (Amazon Ads Console format) ──────────
# Columns used: Date, Purchased ASIN, "14 Day Total Sales "
# This report gives SB-attributed SALES (not spend).
# SB spend is already included in HistoricalAsin PPC Cost → no double-counting.
def load_sb(path: Path | None, child_to_parent: dict) -> dict:
    """Returns {parent_asin: {week: {sbsp, sb_attr}}}"""
    sb: dict = defaultdict(lambda: defaultdict(lambda: {"sbsp": 0.0, "sb_attr": 0.0}))
    if not path or not Path(path).exists():
        return sb

    import re as _re

    def _parse_money(v: str) -> float:
        return float(_re.sub(r"[^\d.]", "", str(v).strip())) if v and v.strip() else 0.0

    def _parse_sb_date(s: str):
        for fmt in ("%b %d, %Y", "%B %d, %Y", "%Y-%m-%d"):
            try: return datetime.strptime(s.strip().strip('"'), fmt).date()
            except: pass
        return None

    # Column name has a trailing space in Amazon's export — handle both
    SALES_COL = None

    with open(path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for r in reader:
            if SALES_COL is None:
                # Detect the sales column once (trailing-space variant)
                SALES_COL = next(
                    (k for k in r.keys() if "14 Day Total Sales" in k and "Click" not in k),
                    "14 Day Total Sales"
                )
            d  = _parse_sb_date(r.get("Date", ""))
            wk = _get_week(d) if d else None
            if not wk: continue

            child = r.get("Purchased ASIN", "").strip()
            parent = child_to_parent.get(child, child)
            if parent not in PARENT_COLORS: continue

            sb[parent][wk]["sb_attr"] += _parse_money(r.get(SALES_COL, 0))
            # sbsp stays 0 — SB spend already captured in PPC Cost total

    return sb

# ── Extract W1-W4 from existing SOURCE_HTML (preserves SP/SD/SB breakdown) ──
def load_frozen_data(html_path: Path, frozen_weeks: list) -> tuple[dict, dict]:
    """Read PARENTS + CHILD_DATA from existing dashboard HTML, return only frozen weeks."""
    with open(html_path, encoding="utf-8") as f:
        html = f.read()

    m = re.search(r"const PARENTS = (\{.+?\});", html, re.DOTALL)
    parents_raw = json.loads(m.group(1)) if m else {}

    m2 = re.search(r"const CHILD_DATA = (\[.+?\]);", html, re.DOTALL)
    children_raw = json.loads(m2.group(1)) if m2 else []

    # frozen_parents: {parent_asin: {W1: {...}, W2: {...}, ...}}
    frozen_parents: dict[str, dict] = {}
    for pid, p in parents_raw.items():
        if pid in PARENT_COLORS:
            frozen_parents[pid] = {w: p["weeks"][w] for w in frozen_weeks if w in p.get("weeks", {})}

    # frozen_children: {child_asin: {"parent": ..., "name": ..., "weeks": {W1: ...}}}
    frozen_children: dict[str, dict] = {}
    for c in children_raw:
        asin = c.get("asin", "")
        parent = c.get("parent", "")
        if asin and parent in PARENT_COLORS:
            frozen_children[asin] = {
                "parent": parent,
                "name":   c.get("name", ""),
                "color":  c.get("color", PARENT_COLORS[parent]),
                "weeks":  {w: c["weeks"][w] for w in frozen_weeks if w in c.get("weeks", {})},
            }
    return frozen_parents, frozen_children


# ── Build PARENTS + CHILD_DATA (frozen W1-W4 + fresh CSV weeks) ───────────
def build_data(weekly: dict, child_to_parent: dict, asin_to_name: dict,
               sb_data: dict, frozen_parents: dict, frozen_children: dict) -> tuple[dict, list]:

    new_weeks = [w for w in WEEKS if w not in FROZEN_WEEKS]

    # Union of all known children (frozen + CSV)
    all_children: dict[str, str] = {}   # asin → parent_asin
    for asin, fc in frozen_children.items():
        all_children[asin] = fc["parent"]
    for asin in weekly:
        parent = child_to_parent.get(asin, asin)
        if parent in PARENT_COLORS:
            all_children[asin] = parent

    # ── CHILD_DATA ─────────────────────────────────────────────────────────
    child_data: list[dict] = []
    for asin, parent in all_children.items():
        weeks_obj: dict = {}

        # Frozen weeks: use preserved data
        fc = frozen_children.get(asin, {})
        for w in FROZEN_WEEKS:
            weeks_obj[w] = fc.get("weeks", {}).get(w, {"sales":0,"spend":0,"units":0,"organic":0})

        # New weeks: compute from CSV
        for w in new_weeks:
            wd = weekly.get(asin, {}).get(w, {})
            weeks_obj[w] = {
                "sales":   round(wd.get("sales",   0), 2),
                "spend":   round(wd.get("spend",   0), 2),
                "units":   int(wd.get("units",     0)),
                "organic": int(wd.get("organic",   0)),
            }

        total_sales = sum(weeks_obj[w]["sales"] for w in WEEKS)
        child_data.append({
            "asin":         asin,
            "parent":       parent,
            "parent_short": PARENT_SHORTS.get(parent, ""),
            "color":        PARENT_COLORS.get(parent, "#888"),
            "name":         fc.get("name", asin_to_name.get(asin, asin)),
            "weeks":        {w: weeks_obj[w] for w in WEEKS},
            "total_sales":  round(total_sales, 2),
        })
    child_data.sort(key=lambda x: -x["total_sales"])

    # ── PARENTS ────────────────────────────────────────────────────────────
    parent_children: dict[str, list[str]] = defaultdict(list)
    for c in child_data:
        parent_children[c["parent"]].append(c["asin"])

    parents: dict[str, dict] = {}
    for parent, children in parent_children.items():
        weeks_obj = {}

        # Frozen weeks: use preserved parent-level data (has spsd/sbsp split)
        fp = frozen_parents.get(parent, {})
        for w in FROZEN_WEEKS:
            weeks_obj[w] = fp.get(w, {
                "sales":0,"spsd":0,"sbsp":0,"spend":0,
                "units":0,"organic":0,"ppc":0,"profits":0,"tacos":None
            })

        # New weeks: aggregate fresh from CSV
        for w in new_weeks:
            sales   = sum(weekly.get(a,{}).get(w,{}).get("sales",   0) for a in children)
            spsd    = sum(weekly.get(a,{}).get(w,{}).get("spend",   0) for a in children)
            units   = sum(weekly.get(a,{}).get(w,{}).get("units",   0) for a in children)
            organic = sum(weekly.get(a,{}).get(w,{}).get("organic", 0) for a in children)
            ppc     = sum(weekly.get(a,{}).get(w,{}).get("ppc",     0) for a in children)
            profits = sum(weekly.get(a,{}).get(w,{}).get("profits", 0) for a in children)
            sbsp    = sb_data.get(parent, {}).get(w, {}).get("sbsp", 0)
            spend   = round(spsd + sbsp, 2)
            tacos   = round(spend / sales * 100, 1) if sales > 0 else None
            weeks_obj[w] = {
                "sales": round(sales,2), "spsd": round(spsd,2), "sbsp": round(sbsp,2),
                "spend": spend, "units": units, "organic": organic,
                "ppc": ppc, "profits": round(profits,2), "tacos": tacos,
            }

        tot_s    = sum(weeks_obj[w]["sales"] for w in WEEKS)
        tot_e    = sum(weeks_obj[w]["spend"] for w in WEEKS)
        sb_attr  = sum(sb_data.get(parent, {}).get(w, {}).get("sb_attr", 0) for w in WEEKS)
        tacos_nw = round(tot_e / tot_s * 100, 1) if tot_s > 0 else None
        parents[parent] = {
            "name":        asin_to_name.get(parent, PARENT_SHORTS.get(parent, "")),
            "short":       PARENT_SHORTS.get(parent, ""),
            "color":       PARENT_COLORS.get(parent, "#888"),
            "children":    children,
            "weeks":       weeks_obj,
            "total_sales": round(tot_s, 2),
            "total_spend": round(tot_e, 2),
            "total_spsd":  round(sum(weeks_obj[w].get("spsd",0) for w in WEEKS), 2),
            "tacos_4w":    tacos_nw,
            "sb_attr":     round(sb_attr, 2),
        }
    return parents, child_data

# ═══════════════════════════════════════════════════════════════════════════
# ── HTML TRANSFORMATION ────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════

def apply_light_theme(html: str) -> str:
    """Convert dark CSS vars → light theme, add Inter font, shadows, etc."""

    # 1. Google Fonts: Syne → Inter
    html = html.replace(
        "family=Syne:wght@400;600;700;800&",
        "family=Inter:wght@400;500;600;700;800&"
    )

    # 2. CSS variables
    for old, new in [
        ("--bg:#080a0f",    "--bg:#f1f5f9"),
        ("--bg2:#0e1117",   "--bg2:#ffffff"),
        ("--bg3:#141820",   "--bg3:#f8fafc"),
        ("--border:#1e2330",   "--border:#e2e8f0"),
        ("--border2:#252d3d",  "--border2:#cbd5e1"),
        ("--text:#e4e8f0",  "--text:#0f172a"),
        ("--text2:#8892a4", "--text2:#475569"),
        ("--text3:#454e60", "--text3:#94a3b8"),
        ("--accent:#5b8af0","--accent:#2563eb"),
        ("--green:#1fdb8a", "--green:#16a34a"),
        ("--amber:#f5a623", "--amber:#d97706"),
        ("--red:#f04b4b",   "--red:#dc2626"),
        ("--display:'Syne',sans-serif", "--display:'Inter',sans-serif"),
    ]:
        html = html.replace(old, new)

    # 3. Body
    html = html.replace(
        "body{background:var(--bg);color:var(--text);font-family:var(--body);font-size:14px;min-height:100vh;}",
        "body{background:var(--bg);color:var(--text);font-family:var(--body);font-size:15px;line-height:1.6;min-height:100vh;}"
    )

    # 4. Nav — full-width shell + centered .nav-inner
    html = html.replace(
        "nav{display:flex;align-items:center;background:var(--bg2);border-bottom:1px solid var(--border);padding:0 20px;height:54px;position:sticky;top:0;z-index:100;gap:0;}",
        "nav{background:var(--bg2);border-bottom:1px solid var(--border);height:54px;position:sticky;top:0;z-index:100;box-shadow:0 1px 4px rgba(0,0,0,.05);}"
        "\n.nav-inner{max-width:1600px;margin:0 auto;display:flex;align-items:center;height:54px;padding:0 32px;gap:0;}"
    )
    html = html.replace(
        '<nav>\n  <div class="nav-brand">',
        '<nav>\n  <div class="nav-inner">\n  <div class="nav-brand">'
    )
    html = html.replace(
        "· SP+SD+SB · TACOS ≤70%</div>\n</nav>",
        f"· SP+SD+SB · TACOS ≤{TACOS_TARGET}%</div>\n  </div>\n</nav>"
    )

    # 5. Panel: wide + centered
    html = html.replace(
        ".panel{display:none;padding:24px;min-height:calc(100vh - 54px);}.panel.active{display:block;}",
        ".panel{display:none;padding:32px;min-height:calc(100vh - 54px);max-width:1600px;margin:0 auto;}.panel.active{display:block;}"
    )

    # 6. Table hover
    html = html.replace("rgba(255,255,255,.02)", "rgba(15,23,42,.025)")
    html = html.replace("rgba(255,255,255,.03)", "rgba(15,23,42,.03)")

    # 7. Card styling
    html = html.replace(
        ".chart-card{background:var(--bg2);border:1px solid var(--border);border-radius:8px;padding:20px;}",
        ".chart-card{background:var(--bg2);border:1px solid var(--border);border-radius:10px;padding:20px;box-shadow:0 1px 5px rgba(0,0,0,.06);}"
    )
    html = html.replace(
        "border-radius:8px;overflow:hidden;margin-bottom:20px;}",
        "border-radius:10px;overflow:hidden;margin-bottom:20px;box-shadow:0 1px 5px rgba(0,0,0,.06);}"
    )
    html = html.replace(
        ".action-card{background:var(--bg2);border:1px solid var(--border);border-radius:10px;padding:20px;margin-bottom:12px;}",
        ".action-card{background:var(--bg2);border:1px solid var(--border);border-radius:10px;padding:20px;margin-bottom:12px;box-shadow:0 1px 4px rgba(0,0,0,.05);}"
    )
    html = html.replace(
        ".table-wrap{overflow-x:auto;border-radius:8px;border:1px solid var(--border);}",
        ".table-wrap{overflow-x:auto;border-radius:10px;border:1px solid var(--border);box-shadow:0 1px 5px rgba(0,0,0,.05);}"
    )
    html = html.replace(".kpi-card{background:var(--bg2);padding:16px 18px;}",
                        ".kpi-card{background:var(--bg2);padding:18px 22px;}")

    # 8. Canvas — donut hole white
    html = html.replace("ctx.fillStyle='#0e1117';ctx.fill();",
                        "ctx.fillStyle='#ffffff';ctx.fill();")

    # 9. Canvas quadrant text colors
    for old, new in [
        ("ctx.fillStyle='#8892a4';ctx.font='10px Outfit",       "ctx.fillStyle='#64748b';ctx.font='10px Outfit"),
        ("ctx.fillStyle='#454e60';ctx.font='11px JetBrains",    "ctx.fillStyle='#94a3b8';ctx.font='11px JetBrains"),
        ("ctx.fillStyle='#5b8af0';ctx.font='bold 13px Syne",    "ctx.fillStyle='#2563eb';ctx.font='bold 13px Inter"),
        ("ctx.fillStyle='#454e60';ctx.font='12px JetBrains",    "ctx.fillStyle='#64748b';ctx.font='12px JetBrains"),
        ("ctx.fillStyle='#5b8af0';ctx.font='bold 20px JetBrains","ctx.fillStyle='#2563eb';ctx.font='bold 20px JetBrains"),
        ("ctx.strokeStyle='#5b8af0';ctx.lineWidth=1.5;",         "ctx.strokeStyle='#2563eb';ctx.lineWidth=1.5;"),
        ("ctx.font='bold 20px Syne,sans-serif'",                 "ctx.font='bold 20px Inter,sans-serif'"),
        ("ctx.font='bold 13px Syne,sans-serif'",                 "ctx.font='bold 13px Inter,sans-serif'"),
    ]:
        html = html.replace(old, new)

    # 10. Quadrant badge / accent colors (dark theme values → light theme)
    for old, new in [
        ("'#f04b4b'", "'#dc2626'"), ("'#f5a623'", "'#d97706'"),
        ("'#5b8af0'", "'#2563eb'"), ("'#1fdb8a'", "'#16a34a'"),
        ("rgba(240,75,75,.07)",  "rgba(220,38,38,.05)"),
        ("rgba(245,166,35,.07)", "rgba(217,119,6,.05)"),
        ("rgba(91,138,240,.07)", "rgba(37,99,235,.05)"),
        ("rgba(31,219,138,.07)", "rgba(22,163,74,.05)"),
        ("rgba(240,75,75,.12)",  "rgba(220,38,38,.1)"),
        ("rgba(245,166,35,.12)", "rgba(217,119,6,.1)"),
        ("rgba(91,138,240,.12)", "rgba(37,99,235,.1)"),
        ("rgba(31,219,138,.15)", "rgba(22,163,74,.12)"),
        ("rgba(240,75,75,.04)",  "rgba(220,38,38,.04)"),
    ]:
        html = html.replace(old, new)

    # 11. Compact spacing — table rows + legend lists
    html = html.replace(
        "tbody td{padding:10px 12px;",
        "tbody td{padding:6px 10px;"
    )
    html = html.replace(
        "thead th{background:var(--bg3);color:var(--text3);font-size:9px;text-transform:uppercase;letter-spacing:.1em;padding:10px 12px;",
        "thead th{background:var(--bg3);color:var(--text3);font-size:9px;text-transform:uppercase;letter-spacing:.1em;padding:7px 10px;"
    )
    # Fix childTable blank space: override table width:100% for childTable only
    html = html.replace(
        "table{width:100%;border-collapse:collapse;}",
        "table{width:100%;border-collapse:collapse;}\n"
        "#childTable td,#childTable th{white-space:nowrap;}\n"
        "#childTable{table-layout:fixed;}"
    )
    # Legend list: reduce gap and max-height
    html = html.replace(
        'id="salesList" style="flex:1;display:flex;flex-direction:column;gap:3px;overflow-y:auto;max-height:250px"',
        'id="salesList" style="flex:1;display:flex;flex-direction:column;gap:0;overflow-y:auto;max-height:220px"'
    )
    html = html.replace(
        'id="adsList" style="flex:1;display:flex;flex-direction:column;gap:3px;overflow-y:auto;max-height:250px"',
        'id="adsList" style="flex:1;display:flex;flex-direction:column;gap:0;overflow-y:auto;max-height:220px"'
    )
    # Legend row item padding
    html = html.replace(
        "padding:4px 0;border-bottom:1px solid var(--border)",
        "padding:3px 0;border-bottom:1px solid var(--border)"
    )

    return html


def inject_data(html: str, parents: dict, child_data: list) -> str:
    """Replace data constants block + currency + TACOS target + fix JS hardcoded weeks."""
    nw = len(WEEKS)
    weeks_arr  = json.dumps(WEEKS)
    wlabels_js = json.dumps(W_LABELS)

    # Build the new constants block
    new_block = (
        f"const PARENTS = {json.dumps(parents, ensure_ascii=False)};\n"
        f"const CHILD_DATA = {json.dumps(child_data, ensure_ascii=False)};\n\n"
        f"const ZH = {json.dumps(ZH_PARENTS, ensure_ascii=False)};\n"
        f"const CHILD_ZH = {json.dumps(ZH_CHILDREN, ensure_ascii=False)};\n\n"
        f"const TACOS_TARGET = {TACOS_TARGET};\n"
        f"const WEEKS = {weeks_arr};\n"
        f"const W_LABELS = {wlabels_js};"
    )
    # Replace the whole data section (PARENTS … W_LABELS)
    _nb = new_block  # capture for lambda
    html = re.sub(
        r"const PARENTS = .+?const W_LABELS = \{[^}]+\};",
        lambda _: _nb,
        html,
        flags=re.DOTALL,
    )

    # ── FIX: _t1 cache was hardcoded as ['all','W1','W2','W3','W4']
    # Replace with dynamic version that uses the WEEKS constant.
    html = html.replace(
        "['all','W1','W2','W3','W4'].forEach(mode=>{",
        "['all',...WEEKS].forEach(mode=>{"
    )

    # Currency: keep $ for US, swap if needed
    if CURRENCY != "$":
        html = html.replace(
            "const fmt = (v,d=0) => v==null?'—':'$'+v.toLocaleString('en-US',",
            f"const fmt = (v,d=0) => v==null?'—':'{CURRENCY}'+v.toLocaleString('{LOCALE}',"
        )

    # TACOS KPI hardcoded refs
    html = html.replace("'⚠ Above 70%'",  f"'⚠ Above {TACOS_TARGET}%'")
    html = html.replace('"⚠ Above 70%"',  f'"⚠ Above {TACOS_TARGET}%"')
    html = html.replace(
        '<div class="kpi-value kpi-green">70%</div>',
        f'<div class="kpi-value kpi-green">{TACOS_TARGET}%</div>'
    )
    html = html.replace("acct<=70?",  f"acct<={TACOS_TARGET}?")
    html = html.replace("acct<=84?",  f"acct<={int(TACOS_TARGET*1.2)}?")

    # Dynamic "NW 合計" label (replace "4W 合計" with actual count)
    html = html.replace("4W 合計", f"{nw}W 合計")
    # Dynamic "NW Sales" label in action tab template literal
    html = html.replace("4W Sales ${fmt(", f"{nw}W Sales ${{fmt(")

    # ── FIX: childTable blank space — inject colgroup + table-layout:fixed via JS
    html = html.replace(
        "tbl.innerHTML=`<thead>",
        "// Fixed column widths via colgroup — eliminates blank space\n"
        "  const nWeeks=weeks.length;\n"
        "  const colDefs=[220,58,...Array(nWeeks*3).fill(0).flatMap((_,i)=>i%3===0?[82]:i%3===1?[72]:[60])];\n"
        "  const cg='<colgroup>'+colDefs.map(w=>`<col style=\"width:${w}px\">`).join('')+'</colgroup>';\n"
        "  tbl.innerHTML=`${cg}<thead>"
    )
    # Close the tbl.innerHTML block properly (add table-layout fix after)
    html = html.replace(
        "</tfoot>`;\n}",
        "</tfoot>`;\n"
        "  tbl.style.tableLayout='fixed';\n"
        "  tbl.style.width='auto';\n"
        "  requestAnimationFrame(()=>{\n"
        "    const rows=tbl.querySelectorAll('thead tr');\n"
        "    if(rows[0]&&rows[1]){\n"
        "      const h=rows[0].getBoundingClientRect().height;\n"
        "      rows[1].querySelectorAll('th').forEach(th=>th.style.top=h+'px');\n"
        "    }\n"
        "  });\n"
        "}",
        1  # only first occurrence
    )

    # ── FIX: inject freeze pane CSS and childTable wrapper
    freeze_css = (
        "\n/* ── childTable freeze pane ── */\n"
        "#childTable-wrap{max-height:calc(100vh - 160px);overflow:auto;border-radius:10px;"
        "border:1px solid var(--border);box-shadow:0 1px 5px rgba(0,0,0,.05);}\n"
        "#childTable thead tr:nth-child(1) th{position:sticky;top:0;z-index:4;background:var(--bg3);}\n"
        "#childTable thead tr:nth-child(2) th{position:sticky;z-index:3;background:var(--bg2);}\n"
        "#childTable thead tr:nth-child(1) th.col-freeze{z-index:6;}\n"
        "#childTable thead tr:nth-child(2) th.col-freeze{z-index:5;}\n"
        "#childTable th.col-freeze,#childTable td.col-freeze{position:sticky;left:0;z-index:2;"
        "box-shadow:2px 0 4px -1px rgba(0,0,0,.08);}\n"
        "#childTable tbody td.col-freeze{background:var(--bg2);}\n"
        "#childTable .parent-row td.col-freeze{background:inherit;}\n"
        "#childTable tfoot td.col-freeze{background:var(--bg3);}\n"
    )
    html = html.replace("</style>", freeze_css + "</style>", 1)

    # Wrap childTable div with freeze pane id
    html = html.replace(
        '<div class="table-wrap"><table id="childTable"></table></div>',
        '<div id="childTable-wrap"><table id="childTable"></table></div>'
    )

    return html


def inject_week_buttons(html: str) -> str:
    """Replace the hardcoded week-filter button strip with dynamic buttons."""
    nw = len(WEEKS)
    btns = (
        f'<button class="week-btn active" onclick="switchWeek(\'all\',this)">{nw}W 合計</button>\n'
    )
    for wk, lbl in W_LABELS.items():
        short = lbl.replace("–", "/")
        btns += f'    <button class="week-btn" onclick="switchWeek(\'{wk}\',this)">{wk} {short}</button>\n'

    # Regex: find the week-btn div from 4W 合計 through last button
    html = re.sub(
        r'<button class="week-btn active" onclick="switchWeek\(\'all\',this\)">.*?</button>(\s*<button class="week-btn"[^>]*>.*?</button>)+',
        btns.rstrip(),
        html,
        flags=re.DOTALL,
    )
    return html


def inject_title_labels(html: str) -> str:
    """Update page title, nav brand, period labels."""
    nw = len(WEEKS)
    html = html.replace(
        "<title>DAIKEN · US Market — Feb 2026</title>",
        f"<title>{CLIENT_NAME} · {MARKET} Market — {REPORT_PERIOD}</title>"
    )
    # Nav brand (keep DAIKEN US tag)
    html = html.replace(
        '<div class="nav-brand">DAIKEN <span class="market-tag">US</span></div>',
        f'<div class="nav-brand">{CLIENT_NAME} <span class="market-tag">{MARKET}</span></div>'
    )
    # Period heading inside Tab 1
    html = html.replace(
        "Sales &amp; Ad Spend — Feb 2026",
        f"Sales &amp; Ad Spend — {REPORT_PERIOD}"
    )
    html = html.replace(
        "全產品線佔比分析 · US Market",
        f"全產品線佔比分析 · {MARKET} Market"
    )
    # Canvas title
    html = html.replace("'DAIKEN US · Feb 2026'",
                        f"'{CLIENT_NAME} {MARKET} · {REPORT_PERIOD}'")
    html = html.replace('"DAIKEN US · Feb 2026"',
                        f'"{CLIENT_NAME} {MARKET} · {REPORT_PERIOD}"')
    return html


# ═══════════════════════════════════════════════════════════════════════════
# ── MAIN ────────────────────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("─" * 56)
    print(f"  Client : {CLIENT_NAME} · {MARKET}")
    print(f"  Period : {REPORT_PERIOD}")
    print(f"  Weeks  : {', '.join(WEEKS)}")
    print("─" * 56)

    # 1. Load reference data
    child_to_parent, asin_to_name = load_products(PRODUCTS_CSV)
    weekly = load_sales(SALES_CSV)
    sb_data = load_sb(SB_CSV, child_to_parent)

    # 2. Load frozen W1-W4 from original HTML, compute new weeks from CSV
    frozen_parents, frozen_children = load_frozen_data(SOURCE_HTML, FROZEN_WEEKS)
    print(f"  Frozen  : {', '.join(FROZEN_WEEKS)} (from {SOURCE_HTML.name})")
    print(f"  New     : {', '.join(w for w in WEEKS if w not in FROZEN_WEEKS)} (from CSV)")

    # 3. Build data model (merge frozen + CSV)
    parents, child_data = build_data(weekly, child_to_parent, asin_to_name, sb_data,
                                     frozen_parents, frozen_children)

    print(f"\n  {'Product':<14}  {'Sales':>10}  {'Spend':>8}  {'TACOS':>7}  Children")
    print("  " + "─" * 54)
    for pid, p in sorted(parents.items(), key=lambda x: -x[1]["total_sales"]):
        zh = ZH_PARENTS.get(pid, PARENT_SHORTS.get(pid, pid))
        tc = f"{p['tacos_4w']}%" if p['tacos_4w'] else "—"
        print(f"  {zh:<14}  {CURRENCY}{p['total_sales']:>9,.0f}  {CURRENCY}{p['total_spend']:>7,.0f}  {tc:>7}  {len(p['children'])} child ASINs")

    # 3. Load base HTML and transform
    with open(SOURCE_HTML, encoding="utf-8") as f:
        html = f.read()

    html = apply_light_theme(html)
    html = inject_data(html, parents, child_data)
    html = inject_week_buttons(html)
    html = inject_title_labels(html)

    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\n  ✓ Output → {OUTPUT_HTML.name}  ({len(html):,} chars)")
    print("─" * 56)
