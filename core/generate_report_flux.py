#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════════╗
║  Flux — Multi-Market Dashboard Generator                                ║
║  ─────────────────────────────────────────                              ║
║  Generates per-market dashboards (AU/UK/DE/US/CA) + tabbed wrapper.    ║
║  Input:  clients/flux/input/{market}/                                   ║
║  Output: output/flux/{market}.html  +  flux/index.html (wrapper)       ║
╚══════════════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations
import csv, json, re, os
from datetime import datetime, date
from collections import defaultdict, OrderedDict
from pathlib import Path

# ═══════════════════════════════════════════════════════════════════════════
# ── CONFIG ────────────────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════

CLIENT_NAME   = "Flux"
TACOS_TARGET  = 30
REPORT_PERIOD = "Feb–Mar 2026"

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
WEEKS = list(WEEK_RANGES.keys())
FROZEN_WEEKS: list[str] = []

MARKETS = OrderedDict([
    ("AU", {"currency": "A$",  "locale": "en-AU", "flag": "🇦🇺"}),
    ("UK", {"currency": "£",   "locale": "en-GB", "flag": "🇬🇧"}),
    ("DE", {"currency": "€",   "locale": "de-DE", "flag": "🇩🇪"}),
    ("US", {"currency": "$",   "locale": "en-US", "flag": "🇺🇸"}),
    ("CA", {"currency": "CA$", "locale": "en-CA", "flag": "🇨🇦"}),
])

BASE_DIR    = Path("/Users/koda/amazon-autopilot")
INPUT_BASE  = BASE_DIR / "clients/flux/input"
OUTPUT_DIR  = BASE_DIR / "output/flux"
DEPLOY_DIR  = BASE_DIR / "flux"
# Base HTML template (dark-theme) — used as skeleton for all markets
SOURCE_HTML = BASE_DIR / "clients/daiken/input/DAIKEN_Dashboard_Feb2026.html"

AUTO_COLORS = [
    "#3b82f6", "#a855f7", "#f59e0b", "#22c55e", "#ef4444",
    "#06b6d4", "#f97316", "#ec4899", "#8b5cf6", "#14b8a6",
    "#f43f5e", "#84cc16", "#0ea5e9", "#d946ef", "#facc15",
]


# ═══════════════════════════════════════════════════════════════════════════
# ── DATA PROCESSING ──────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════

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

def load_products(path: Path) -> tuple[dict, dict]:
    child_to_parent: dict[str, str] = {}
    asin_to_name: dict[str, str]    = {}
    with open(path, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            a = r["ASIN"].strip()
            child_to_parent[a] = r["Parent ASIN"].strip()
            asin_to_name[a]    = r["Title"].strip()
    return child_to_parent, asin_to_name

def load_sales(path: Path) -> tuple[dict, dict]:
    """Returns (weekly_per_asin, sb_spend_per_week).
    sb_spend_per_week: total SB spend per week from "Sponsored Brands..." rows.
    """
    weekly: dict = defaultdict(lambda: defaultdict(
        lambda: {"sales": 0.0, "spend": 0.0, "units": 0, "organic": 0,
                 "ppc": 0, "profits": 0.0}))
    sb_spend: dict = defaultdict(float)  # week -> total SB spend
    with open(path, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            d  = _parse_date(r.get("Date", ""))
            wk = _get_week(d) if d else None
            if not wk: continue
            a = r.get("ASIN", "").strip()
            if not a: continue
            # SB spend rows: ASIN = "Sponsored Brands Product Collection/Brand Video"
            if not a.startswith("B0"):
                sb_spend[wk] += _pf(r.get("PPC Cost", 0))
                continue
            wd = weekly[a][wk]
            wd["sales"]   += _pf(r.get("Sales",           0))
            wd["spend"]   += _pf(r.get("PPC Cost",         0))
            wd["units"]   += int(_pf(r.get("Units",        0)))
            wd["organic"] += int(_pf(r.get("Organic Units",0)))
            wd["ppc"]     += int(_pf(r.get("PPC Orders",   0)))
            wd["profits"] += _pf(r.get("Profits",          0))
    return weekly, dict(sb_spend)

def load_sb(path: Path | None, child_to_parent: dict, parent_colors: dict) -> dict:
    sb: dict = defaultdict(lambda: defaultdict(lambda: {"sbsp": 0.0, "sb_attr": 0.0}))
    if not path or not Path(path).exists():
        return sb
    def _parse_money(v: str) -> float:
        return float(re.sub(r"[^\d.]", "", str(v).strip())) if v and v.strip() else 0.0
    def _parse_sb_date(s: str):
        for fmt in ("%b %d, %Y", "%B %d, %Y", "%Y-%m-%d"):
            try: return datetime.strptime(s.strip().strip('"'), fmt).date()
            except: pass
        return None
    SALES_COL = None
    with open(path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for r in reader:
            if SALES_COL is None:
                SALES_COL = next(
                    (k for k in r.keys() if "14 Day Total Sales" in k and "Click" not in k),
                    "14 Day Total Sales"
                )
            d  = _parse_sb_date(r.get("Date", ""))
            wk = _get_week(d) if d else None
            if not wk: continue
            child = r.get("Purchased ASIN", "").strip()
            parent = child_to_parent.get(child, child)
            if parent not in parent_colors: continue
            sb[parent][wk]["sb_attr"] += _parse_money(r.get(SALES_COL, 0))
    return sb

def auto_detect_parents(child_to_parent: dict, asin_to_name: dict) -> tuple[dict, dict]:
    """Auto-generate PARENT_COLORS and PARENT_SHORTS from Products.csv data."""
    unique_parents = sorted(set(child_to_parent.values()))
    colors = {}
    shorts = {}
    for i, p in enumerate(unique_parents):
        colors[p] = AUTO_COLORS[i % len(AUTO_COLORS)]
        # Use first 30 chars of title as short name
        raw = asin_to_name.get(p, p)
        shorts[p] = raw[:30] if raw != p else p
    return colors, shorts

def build_data(weekly: dict, child_to_parent: dict, asin_to_name: dict,
               sb_data: dict, parent_colors: dict, parent_shorts: dict,
               sb_spend_weekly: dict | None = None) -> tuple[dict, list]:
    new_weeks = WEEKS  # all weeks are fresh (no frozen)
    if sb_spend_weekly is None:
        sb_spend_weekly = {}

    all_children: dict[str, str] = {}
    for asin in weekly:
        parent = child_to_parent.get(asin, asin)
        if parent in parent_colors:
            all_children[asin] = parent

    # CHILD_DATA
    child_data: list[dict] = []
    for asin, parent in all_children.items():
        weeks_obj: dict = {}
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
            "parent_short": parent_shorts.get(parent, ""),
            "color":        parent_colors.get(parent, "#888"),
            "name":         asin_to_name.get(asin, asin),
            "weeks":        {w: weeks_obj[w] for w in WEEKS},
            "total_sales":  round(total_sales, 2),
        })
    child_data.sort(key=lambda x: -x["total_sales"])

    # PARENTS
    parent_children: dict[str, list[str]] = defaultdict(list)
    for c in child_data:
        parent_children[c["parent"]].append(c["asin"])

    # Pre-compute SB attributed sales per parent per week for proportional distribution
    sb_attr_by_parent_week: dict = defaultdict(lambda: defaultdict(float))
    for parent in parent_children:
        for w in new_weeks:
            sb_attr_by_parent_week[parent][w] = sb_data.get(parent, {}).get(w, {}).get("sb_attr", 0)

    parents: dict[str, dict] = {}
    for parent, children in parent_children.items():
        weeks_obj = {}
        for w in new_weeks:
            sales   = sum(weekly.get(a,{}).get(w,{}).get("sales",   0) for a in children)
            spsd    = sum(weekly.get(a,{}).get(w,{}).get("spend",   0) for a in children)
            units   = sum(weekly.get(a,{}).get(w,{}).get("units",   0) for a in children)
            organic = sum(weekly.get(a,{}).get(w,{}).get("organic", 0) for a in children)
            ppc     = sum(weekly.get(a,{}).get(w,{}).get("ppc",     0) for a in children)
            profits = sum(weekly.get(a,{}).get(w,{}).get("profits", 0) for a in children)
            # Distribute total SB spend proportionally by SB attributed sales
            total_sb_spend_wk = sb_spend_weekly.get(w, 0)
            total_sb_attr_wk = sum(sb_attr_by_parent_week[p][w] for p in parent_children)
            if total_sb_attr_wk > 0 and total_sb_spend_wk > 0:
                sbsp = total_sb_spend_wk * (sb_attr_by_parent_week[parent][w] / total_sb_attr_wk)
            else:
                sbsp = 0.0
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
            "name":        asin_to_name.get(parent, parent_shorts.get(parent, "")),
            "short":       parent_shorts.get(parent, ""),
            "color":       parent_colors.get(parent, "#888"),
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
# ── HTML TRANSFORMATION (parameterized per market) ───────────────────────
# ═══════════════════════════════════════════════════════════════════════════

def apply_light_theme(html: str) -> str:
    """Convert dark CSS vars → light theme. Runs once on base template."""
    html = html.replace(
        "family=Syne:wght@400;600;700;800&",
        "family=Inter:wght@400;500;600;700;800&"
    )
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
    html = html.replace(
        "body{background:var(--bg);color:var(--text);font-family:var(--body);font-size:14px;min-height:100vh;}",
        "body{background:var(--bg);color:var(--text);font-family:var(--body);font-size:15px;line-height:1.6;min-height:100vh;}"
    )
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
        f"· SP+SD+SB · TACOS ≤70%</div>\n</nav>",
        f"· SP+SD+SB · TACOS ≤{TACOS_TARGET}%</div>\n  </div>\n</nav>"
    )
    html = html.replace(
        ".panel{display:none;padding:24px;min-height:calc(100vh - 54px);}.panel.active{display:block;}",
        ".panel{display:none;padding:32px;min-height:calc(100vh - 54px);max-width:1600px;margin:0 auto;}.panel.active{display:block;}"
    )
    html = html.replace("rgba(255,255,255,.02)", "rgba(15,23,42,.025)")
    html = html.replace("rgba(255,255,255,.03)", "rgba(15,23,42,.03)")
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
    html = html.replace("ctx.fillStyle='#0e1117';ctx.fill();",
                        "ctx.fillStyle='#ffffff';ctx.fill();")
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
    html = html.replace("tbody td{padding:10px 12px;", "tbody td{padding:6px 10px;")
    html = html.replace(
        "thead th{background:var(--bg3);color:var(--text3);font-size:9px;text-transform:uppercase;letter-spacing:.1em;padding:10px 12px;",
        "thead th{background:var(--bg3);color:var(--text3);font-size:9px;text-transform:uppercase;letter-spacing:.1em;padding:7px 10px;"
    )
    html = html.replace(
        "table{width:100%;border-collapse:collapse;}",
        "table{width:100%;border-collapse:collapse;}\n"
        "#childTable td,#childTable th{white-space:nowrap;}\n"
        "#childTable{table-layout:fixed;}"
    )
    html = html.replace(
        'id="salesList" style="flex:1;display:flex;flex-direction:column;gap:3px;overflow-y:auto;max-height:250px"',
        'id="salesList" style="flex:1;display:flex;flex-direction:column;gap:0;overflow-y:auto;max-height:220px"'
    )
    html = html.replace(
        'id="adsList" style="flex:1;display:flex;flex-direction:column;gap:3px;overflow-y:auto;max-height:250px"',
        'id="adsList" style="flex:1;display:flex;flex-direction:column;gap:0;overflow-y:auto;max-height:220px"'
    )
    html = html.replace(
        "padding:4px 0;border-bottom:1px solid var(--border)",
        "padding:3px 0;border-bottom:1px solid var(--border)"
    )
    return html


def inject_data(html: str, parents: dict, child_data: list,
                currency: str, locale: str, market: str) -> str:
    """Inject market-specific data, currency, TACOS target."""
    nw = len(WEEKS)
    weeks_arr  = json.dumps(WEEKS)
    wlabels_js = json.dumps(W_LABELS)

    new_block = (
        f"const PARENTS = {json.dumps(parents, ensure_ascii=False)};\n"
        f"const CHILD_DATA = {json.dumps(child_data, ensure_ascii=False)};\n\n"
        f"const ZH = {{}};\n"
        f"const CHILD_ZH = {{}};\n\n"
        f"const TACOS_TARGET = {TACOS_TARGET};\n"
        f"const WEEKS = {weeks_arr};\n"
        f"const W_LABELS = {wlabels_js};"
    )
    _nb = new_block
    html = re.sub(
        r"const PARENTS = .+?const W_LABELS = \{[^}]+\};",
        lambda _: _nb, html, flags=re.DOTALL,
    )
    html = html.replace(
        "['all','W1','W2','W3','W4'].forEach(mode=>{",
        "['all',...WEEKS].forEach(mode=>{"
    )
    # Currency
    if currency != "$":
        html = html.replace(
            "const fmt = (v,d=0) => v==null?'—':'$'+v.toLocaleString('en-US',",
            f"const fmt = (v,d=0) => v==null?'—':'{currency}'+v.toLocaleString('{locale}',"
        )
    # TACOS refs
    html = html.replace("'⚠ Above 70%'",  f"'⚠ Above {TACOS_TARGET}%'")
    html = html.replace('"⚠ Above 70%"',  f'"⚠ Above {TACOS_TARGET}%"')
    html = html.replace(
        '<div class="kpi-value kpi-green">70%</div>',
        f'<div class="kpi-value kpi-green">{TACOS_TARGET}%</div>'
    )
    html = html.replace("acct<=70?",  f"acct<={TACOS_TARGET}?")
    html = html.replace("acct<=84?",  f"acct<={int(TACOS_TARGET*1.2)}?")
    html = html.replace("4W 合計", f"{nw}W 合計")
    html = html.replace("4W Sales ${fmt(", f"{nw}W Sales ${{fmt(")

    # childTable colgroup fix
    html = html.replace(
        "tbl.innerHTML=`<thead>",
        "// Fixed column widths via colgroup\n"
        "  const nWeeks=weeks.length;\n"
        "  const colDefs=[220,58,...Array(nWeeks*3).fill(0).flatMap((_,i)=>i%3===0?[82]:i%3===1?[72]:[60])];\n"
        "  const cg='<colgroup>'+colDefs.map(w=>`<col style=\"width:${w}px\">`).join('')+'</colgroup>';\n"
        "  tbl.innerHTML=`${cg}<thead>"
    )
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
        1
    )
    # Freeze pane CSS
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
    html = html.replace(
        '<div class="table-wrap"><table id="childTable"></table></div>',
        '<div id="childTable-wrap"><table id="childTable"></table></div>'
    )
    return html


def inject_week_buttons(html: str) -> str:
    nw = len(WEEKS)
    btns = f'<button class="week-btn active" onclick="switchWeek(\'all\',this)">{nw}W 合計</button>\n'
    for wk, lbl in W_LABELS.items():
        short = lbl.replace("–", "/")
        btns += f'    <button class="week-btn" onclick="switchWeek(\'{wk}\',this)">{wk} {short}</button>\n'
    html = re.sub(
        r'<button class="week-btn active" onclick="switchWeek\(\'all\',this\)">.*?</button>(\s*<button class="week-btn"[^>]*>.*?</button>)+',
        btns.rstrip(), html, flags=re.DOTALL,
    )
    return html


def inject_title_labels(html: str, market: str) -> str:
    nw = len(WEEKS)
    html = html.replace(
        "<title>DAIKEN · US Market — Feb 2026</title>",
        f"<title>{CLIENT_NAME} · {market} Market — {REPORT_PERIOD}</title>"
    )
    html = html.replace(
        '<div class="nav-brand">DAIKEN <span class="market-tag">US</span></div>',
        f'<div class="nav-brand">{CLIENT_NAME} <span class="market-tag">{market}</span></div>'
    )
    html = html.replace("Sales &amp; Ad Spend — Feb 2026",
                        f"Sales &amp; Ad Spend — {REPORT_PERIOD}")
    html = html.replace("全產品線佔比分析 · US Market",
                        f"全產品線佔比分析 · {market} Market")
    html = html.replace("'DAIKEN US · Feb 2026'",
                        f"'{CLIENT_NAME} {market} · {REPORT_PERIOD}'")
    html = html.replace('"DAIKEN US · Feb 2026"',
                        f'"{CLIENT_NAME} {market} · {REPORT_PERIOD}"')
    return html


def generate_market_html(base_html: str, market: str, mkt_cfg: dict,
                         parents: dict, child_data: list) -> str:
    """Take pre-themed base HTML → inject market-specific data → return final HTML."""
    html = base_html  # already light-themed
    html = inject_data(html, parents, child_data,
                       mkt_cfg["currency"], mkt_cfg["locale"], market)
    html = inject_week_buttons(html)
    html = inject_title_labels(html, market)
    return html


# ═══════════════════════════════════════════════════════════════════════════
# ── TABBED WRAPPER HTML ──────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════

def generate_wrapper(active_markets: list[tuple[str, dict]]) -> str:
    """Generate the tabbed wrapper page with iframes for each active market."""
    first_mkt = active_markets[0][0].lower() if active_markets else "au"

    tabs_html = ""
    for mkt, cfg in active_markets:
        active = " active" if mkt.lower() == first_mkt else ""
        tabs_html += (
            f'    <button class="mkt-btn{active}" '
            f'onclick="switchMkt(\'{mkt.lower()}\',this)">'
            f'{cfg["flag"]} {mkt}</button>\n'
        )

    iframes_html = ""
    for mkt, cfg in active_markets:
        display = "block" if mkt.lower() == first_mkt else "none"
        iframes_html += (
            f'  <iframe id="fr-{mkt.lower()}" src="./{mkt.lower()}.html" '
            f'style="display:{display}" frameborder="0"></iframe>\n'
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Flux — Multi-Market Dashboard</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
  *{{margin:0;padding:0;box-sizing:border-box;}}
  body{{font-family:'Inter',sans-serif;background:#f1f5f9;}}
  .mkt-bar{{
    display:flex;align-items:center;gap:0;
    background:#fff;border-bottom:2px solid #e2e8f0;
    padding:0 24px;height:48px;position:sticky;top:0;z-index:200;
    box-shadow:0 1px 4px rgba(0,0,0,.06);
  }}
  .mkt-bar .brand{{
    font-size:15px;font-weight:800;color:#2563eb;letter-spacing:.04em;
    margin-right:24px;white-space:nowrap;
  }}
  .mkt-btn{{
    border:none;background:none;cursor:pointer;
    font-family:'Inter',sans-serif;font-size:13px;font-weight:600;
    color:#64748b;padding:12px 18px;position:relative;
    transition:color .15s;white-space:nowrap;
  }}
  .mkt-btn:hover{{color:#0f172a;}}
  .mkt-btn.active{{color:#2563eb;}}
  .mkt-btn.active::after{{
    content:'';position:absolute;bottom:-2px;left:12px;right:12px;
    height:3px;background:#2563eb;border-radius:3px 3px 0 0;
  }}
  iframe{{
    width:100%;height:calc(100vh - 48px);border:none;
  }}
</style>
</head>
<body>
<div class="mkt-bar">
  <div class="brand">⚡ Flux</div>
{tabs_html}</div>
{iframes_html}
<script>
function switchMkt(mkt, btn) {{
  document.querySelectorAll('.mkt-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  document.querySelectorAll('iframe').forEach(f => f.style.display = 'none');
  document.getElementById('fr-' + mkt).style.display = 'block';
}}
</script>
</body>
</html>"""


# ═══════════════════════════════════════════════════════════════════════════
# ── MAIN ─────────────────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    DEPLOY_DIR.mkdir(parents=True, exist_ok=True)

    print("═" * 60)
    print(f"  Flux Multi-Market Dashboard Generator")
    print(f"  Period : {REPORT_PERIOD}  ·  Weeks : {', '.join(WEEKS)}")
    print(f"  TACOS  : ≤{TACOS_TARGET}%  ·  Markets : {', '.join(MARKETS.keys())}")
    print("═" * 60)

    # Load base HTML template once
    if not SOURCE_HTML.exists():
        print(f"  ✗ Base template not found: {SOURCE_HTML}")
        raise SystemExit(1)
    with open(SOURCE_HTML, encoding="utf-8") as f:
        base_html = f.read()
    base_html = apply_light_theme(base_html)
    print(f"  ✓ Base template loaded + light theme applied")

    active_markets: list[tuple[str, dict]] = []

    for mkt, cfg in MARKETS.items():
        mkt_lower = mkt.lower()
        input_dir = INPUT_BASE / mkt_lower
        products_csv = input_dir / "Products.csv"
        sales_csv    = input_dir / "HistoricalAsinDateSales.csv"
        sb_csv       = input_dir / "SB_report.csv"

        # Check if market has data
        if not products_csv.exists() or not sales_csv.exists():
            print(f"\n  ⏭  {mkt} — skipped (no CSVs in {input_dir})")
            continue

        print(f"\n{'─' * 60}")
        print(f"  {cfg['flag']}  {mkt} Market  ·  Currency: {cfg['currency']}")
        print(f"{'─' * 60}")

        # 1. Load data
        child_to_parent, asin_to_name = load_products(products_csv)
        weekly, sb_spend_weekly = load_sales(sales_csv)

        # 2. Auto-detect parents
        parent_colors, parent_shorts = auto_detect_parents(child_to_parent, asin_to_name)
        print(f"  Auto-detected {len(parent_colors)} parent ASINs")

        # 3. Load SB data
        sb_data = load_sb(sb_csv, child_to_parent, parent_colors)

        # 4. Build data model (with SB spend distribution)
        parents, child_data = build_data(
            weekly, child_to_parent, asin_to_name, sb_data,
            parent_colors, parent_shorts, sb_spend_weekly
        )
        if sb_spend_weekly:
            total_sb = sum(sb_spend_weekly.values())
            print(f"  SB spend distributed: {cfg['currency']}{total_sb:.2f} across {len(sb_spend_weekly)} weeks")

        # Print summary
        currency = cfg["currency"]
        print(f"\n  {'Product':<30}  {'Sales':>10}  {'Spend':>8}  {'TACOS':>7}")
        print("  " + "─" * 60)
        for pid, p in sorted(parents.items(), key=lambda x: -x[1]["total_sales"]):
            short = parent_shorts.get(pid, pid)[:28]
            tc = f"{p['tacos_4w']}%" if p['tacos_4w'] else "—"
            print(f"  {short:<30}  {currency}{p['total_sales']:>9,.0f}  {currency}{p['total_spend']:>7,.0f}  {tc:>7}")

        # 5. Generate per-market HTML
        market_html = generate_market_html(base_html, mkt, cfg, parents, child_data)

        # Save to output/flux/{market}.html
        out_path = OUTPUT_DIR / f"{mkt_lower}.html"
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(market_html)
        print(f"\n  ✓ {out_path.name}  ({len(market_html):,} chars)")

        # Also copy to deploy dir
        deploy_path = DEPLOY_DIR / f"{mkt_lower}.html"
        with open(deploy_path, "w", encoding="utf-8") as f:
            f.write(market_html)

        active_markets.append((mkt, cfg))

    # Generate tabbed wrapper
    if active_markets:
        wrapper = generate_wrapper(active_markets)
        for dest in [OUTPUT_DIR / "index.html", DEPLOY_DIR / "index.html"]:
            with open(dest, "w", encoding="utf-8") as f:
                f.write(wrapper)
        print(f"\n{'═' * 60}")
        print(f"  ✓ Wrapper → flux/index.html  ({len(active_markets)} markets)")
        print(f"  Markets: {', '.join(m for m,_ in active_markets)}")
        print(f"{'═' * 60}")
    else:
        print(f"\n  ⚠ No markets with data found. Place CSVs in:")
        for mkt in MARKETS:
            print(f"     clients/flux/input/{mkt.lower()}/")
