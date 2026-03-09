#!/usr/bin/env python3
"""
Brain Tea US Market Dashboard Generator
Reads 3 CSVs and produces a single-file HTML dashboard matching the DAIKEN format.
"""

import csv
import json
import os
from collections import defaultdict
from datetime import datetime

# ── Paths ──
BASE = os.path.dirname(os.path.abspath(__file__))
HIST_CSV = os.path.join(BASE, "BRAINTEA_HistoricalAsinDateSales (3).csv")
PROD_CSV = os.path.join(BASE, "BRAINTEA_Products (2).csv")
SB_CSV   = os.path.join(BASE, "BRAINTEA_Sponsored_Brands_Attributed_Purchases_report (2).csv")
OUT_HTML = os.path.join(BASE, "..", "output", "braintea", "BRAINTEA_US_Feb-Mar_2026.html")

# ── Product mapping ──
PARENT_MAP = {
    "B0824GK8BP": {"parent": "B0824GK8BP", "group": "Focus & Memory Tea"},
    "B0CRZRHT7R": {"parent": "B0FD2NHYT2", "group": "Yerba Mate"},
    "B0DKTK9WKM": {"parent": "B0FD2NHYT2", "group": "Yerba Mate"},
    "B0D98N836B": None,  # inactive, skip or ignore
    "B0FD2NHYT2": {"parent": "B0FD2NHYT2", "group": "Yerba Mate"},
}

PARENT_CONFIG = {
    "B0824GK8BP": {
        "name": "Brain Tea Focus & Memory Tea",
        "short": "Focus & Memory Tea",
        "color": "#3b82f6",
        "children": ["B0824GK8BP"],
    },
    "B0FD2NHYT2": {
        "name": "Brain Tea Yerba Mate",
        "short": "Yerba Mate",
        "color": "#22c55e",
        "children": ["B0CRZRHT7R", "B0DKTK9WKM"],
    },
}

ZH = {
    "B0824GK8BP": "專注記憶茶 Focus Tea",
    "B0FD2NHYT2": "有機瑪黛茶 Yerba Mate",
}

CHILD_ZH = {
    "B0824GK8BP": "專注記憶茶 Focus Tea · 30包",
    "B0CRZRHT7R": "有機瑪黛茶 Yerba Mate · Tea Bags 50ct",
    "B0DKTK9WKM": "有機瑪黛茶 Yerba Mate · Loose Leaf 500g",
}

WEEKS_DEF = [
    ("W1", "Feb 1–7",  datetime(2026,2,1), datetime(2026,2,7)),
    ("W2", "Feb 8–14", datetime(2026,2,8), datetime(2026,2,14)),
    ("W3", "Feb 15–21",datetime(2026,2,15),datetime(2026,2,21)),
    ("W4", "Feb 22–28",datetime(2026,2,22),datetime(2026,2,28)),
    ("W5", "Mar 1–7",  datetime(2026,3,1), datetime(2026,3,7)),
]

WEEK_KEYS = [w[0] for w in WEEKS_DEF]
W_LABELS  = {w[0]: w[1] for w in WEEKS_DEF}

SB_ASIN = "Sponsored Brands Product Collection/Brand Video"

TACOS_TARGET = 15

# ── Helpers ──
def parse_date(s):
    """Parse dates in format 07-Mar-26 or Feb 2, 2026"""
    for fmt in ("%d-%b-%y", "%b %d, %Y"):
        try:
            return datetime.strptime(s.strip().replace('"',''), fmt)
        except ValueError:
            continue
    raise ValueError(f"Cannot parse date: {s}")

def get_week(dt):
    for wk, _, start, end in WEEKS_DEF:
        if start <= dt <= end:
            return wk
    return None

def safe_float(s):
    if not s or s.strip() == '':
        return 0.0
    s = s.strip().replace('$','').replace(',','').replace('%','').replace('"','')
    try:
        return float(s)
    except ValueError:
        return 0.0

# ── Read Historical CSV ──
def read_historical():
    """Returns dict: asin -> week -> {sales, units, organic, ppc_units, ppc_sales, ppc_cost, profits, orders}"""
    data = defaultdict(lambda: defaultdict(lambda: {
        "sales":0, "units":0, "organic":0, "ppc_units":0, "ppc_sales":0,
        "ppc_cost":0, "profits":0, "orders":0, "sessions":0,
    }))
    with open(HIST_CSV, newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            dt = parse_date(row['Date'])
            wk = get_week(dt)
            if not wk:
                continue
            asin = row['ASIN'].strip()
            d = data[asin][wk]
            d['sales']    += safe_float(row.get('Sales','0'))
            d['units']    += int(safe_float(row.get('Units','0')))
            d['organic']  += int(safe_float(row.get('Organic Units','0')))
            d['ppc_units']+= int(safe_float(row.get('PPC Units','0')))
            d['ppc_sales']+= safe_float(row.get('PPC Sales','0'))
            d['ppc_cost'] += safe_float(row.get('PPC Cost','0'))
            d['profits']  += safe_float(row.get('Profits','0'))
            d['orders']   += int(safe_float(row.get('Orders','0')))
            d['sessions'] += int(safe_float(row.get('Sessions','0') or '0'))
    return data

# ── Read SB Attributed Purchases ──
def read_sb_attributed():
    """Returns dict: asin -> week -> sb_attributed_sales"""
    data = defaultdict(lambda: defaultdict(float))
    with open(SB_CSV, newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            dt = parse_date(row['Date'])
            wk = get_week(dt)
            if not wk:
                continue
            asin = row['Purchased ASIN'].strip()
            sales_val = safe_float(row.get('14 Day Total Sales ','0'))
            data[asin][wk] += sales_val
    return data

# ── Main ──
def main():
    hist = read_historical()
    sb_attr = read_sb_attributed()

    # ── Compute SB spend per week ──
    sb_spend_by_week = {}
    for wk in WEEK_KEYS:
        sb_spend_by_week[wk] = hist[SB_ASIN][wk]['ppc_cost']

    # ── Compute SB attributed sales per parent per week ──
    sb_attr_by_parent = defaultdict(lambda: defaultdict(float))
    for asin, weeks in sb_attr.items():
        pm = PARENT_MAP.get(asin)
        if pm is None:
            continue
        parent_id = pm['parent']
        for wk, sales in weeks.items():
            sb_attr_by_parent[parent_id][wk] += sales

    # ── Distribute SB spend proportionally by SB attributed sales (PPC Sales from SB) ──
    sb_spend_allocated = defaultdict(lambda: defaultdict(float))
    for wk in WEEK_KEYS:
        total_sb_sales = sum(sb_attr_by_parent[pid][wk] for pid in PARENT_CONFIG)
        if total_sb_sales > 0:
            for pid in PARENT_CONFIG:
                ratio = sb_attr_by_parent[pid][wk] / total_sb_sales
                sb_spend_allocated[pid][wk] = sb_spend_by_week[wk] * ratio
        else:
            # If no SB attributed sales, distribute evenly
            for pid in PARENT_CONFIG:
                sb_spend_allocated[pid][wk] = sb_spend_by_week[wk] / len(PARENT_CONFIG)

    # ── Build parent data ──
    parents_data = {}
    for pid, cfg in PARENT_CONFIG.items():
        weeks_data = {}
        for wk in WEEK_KEYS:
            sales = sum(hist[c][wk]['sales'] for c in cfg['children'])
            sp_spend = sum(hist[c][wk]['ppc_cost'] for c in cfg['children'])
            sb_sp = sb_spend_allocated[pid][wk]
            total_spend = sp_spend + sb_sp
            units = sum(hist[c][wk]['units'] for c in cfg['children'])
            organic = sum(hist[c][wk]['organic'] for c in cfg['children'])
            ppc_units = sum(hist[c][wk]['ppc_units'] for c in cfg['children'])
            profits = sum(hist[c][wk]['profits'] for c in cfg['children'])
            # Add SB profit impact (negative)
            profits += hist[SB_ASIN][wk]['profits'] * (sb_sp / sb_spend_by_week[wk] if sb_spend_by_week[wk] > 0 else 0)
            tacos = total_spend / sales * 100 if sales > 0 else None

            weeks_data[wk] = {
                "sales": round(sales, 2),
                "spsd": round(sp_spend, 2),
                "sbsp": round(sb_sp, 2),
                "spend": round(total_spend, 2),
                "units": units,
                "organic": organic,
                "ppc": ppc_units,
                "profits": round(profits, 2),
                "tacos": round(tacos, 1) if tacos is not None else None,
            }

        total_sales = sum(weeks_data[w]['sales'] for w in WEEK_KEYS)
        total_spend = sum(weeks_data[w]['spend'] for w in WEEK_KEYS)
        total_spsd  = sum(weeks_data[w]['spsd'] for w in WEEK_KEYS)
        # TACOS over full period (4w = W1-W4 for quadrant, but we use all 5 weeks)
        tacos_4w = total_spend / total_sales * 100 if total_sales > 0 else 0

        # Total SB attributed sales
        sb_attr_total = sum(sb_attr_by_parent[pid][wk] for wk in WEEK_KEYS)

        parents_data[pid] = {
            "name": cfg['name'],
            "short": cfg['short'],
            "color": cfg['color'],
            "children": cfg['children'],
            "weeks": weeks_data,
            "total_sales": round(total_sales, 2),
            "total_spend": round(total_spend, 2),
            "total_spsd": round(total_spsd, 2),
            "tacos_4w": round(tacos_4w, 1),
            "sb_attr": round(sb_attr_total, 2),
        }

    # ── Build child data ──
    child_data = []
    for pid, cfg in PARENT_CONFIG.items():
        for c in cfg['children']:
            weeks = {}
            for wk in WEEK_KEYS:
                h = hist[c][wk]
                weeks[wk] = {
                    "sales": round(h['sales'], 2),
                    "spend": round(h['ppc_cost'], 2),
                    "units": h['units'],
                    "organic": h['organic'],
                }
            total_sales = sum(weeks[w]['sales'] for w in WEEK_KEYS)
            child_name = CHILD_ZH.get(c, c)
            child_data.append({
                "asin": c,
                "parent": pid,
                "parent_short": cfg['short'],
                "color": cfg['color'],
                "name": child_name,
                "weeks": weeks,
                "total_sales": round(total_sales, 2),
            })

    # ── Generate HTML ──
    html = generate_html(parents_data, child_data)

    os.makedirs(os.path.dirname(OUT_HTML), exist_ok=True)
    with open(OUT_HTML, 'w', encoding='utf-8') as f:
        f.write(html)

    fsize = os.path.getsize(OUT_HTML)
    print(f"Dashboard written to: {OUT_HTML}")
    print(f"File size: {fsize:,} bytes ({fsize/1024:.1f} KB)")
    if fsize < 40960:
        print("WARNING: File size is less than 40KB!")
    else:
        print("OK: File size > 40KB")


def generate_html(parents_data, child_data):
    parents_json = json.dumps(parents_data, ensure_ascii=False)
    child_json = json.dumps(child_data, ensure_ascii=False)
    zh_json = json.dumps(ZH, ensure_ascii=False)
    child_zh_json = json.dumps(CHILD_ZH, ensure_ascii=False)
    w_labels_json = json.dumps(W_LABELS, ensure_ascii=False)

    return f'''<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Brain Tea · US Market — Feb–Mar 2026</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;600;700&family=Outfit:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
:root{{
  --bg:#f1f5f9;--bg2:#ffffff;--bg3:#f8fafc;
  --border:#e2e8f0;--border2:#cbd5e1;
  --text:#0f172a;--text2:#475569;--text3:#94a3b8;
  --accent:#059669;--green:#16a34a;--amber:#d97706;--red:#dc2626;
  --mono:'JetBrains Mono',monospace;--display:'Inter',sans-serif;--body:'Outfit',sans-serif;
}}
*{{margin:0;padding:0;box-sizing:border-box;}}
body{{background:var(--bg);color:var(--text);font-family:var(--body);font-size:15px;line-height:1.6;min-height:100vh;}}
nav{{background:var(--bg2);border-bottom:1px solid var(--border);height:54px;position:sticky;top:0;z-index:100;box-shadow:0 1px 4px rgba(0,0,0,.05);}}
.nav-inner{{max-width:1600px;margin:0 auto;display:flex;align-items:center;height:54px;padding:0 32px;gap:0;}}
.nav-brand{{font-family:var(--display);font-size:15px;font-weight:800;color:var(--accent);letter-spacing:.04em;margin-right:24px;white-space:nowrap;display:flex;align-items:center;gap:8px;}}
.market-tag{{font-size:9px;font-family:var(--mono);background:var(--accent);color:#fff;padding:2px 6px;border-radius:3px;font-weight:600;}}
.tabs{{display:flex;gap:2px;flex:1;overflow-x:auto;}}.tabs::-webkit-scrollbar{{display:none;}}
.tab-btn{{padding:0 15px;height:54px;background:none;border:none;color:var(--text2);font-family:var(--body);font-size:12.5px;font-weight:500;cursor:pointer;white-space:nowrap;border-bottom:2px solid transparent;transition:all .15s;}}
.tab-btn:hover{{color:var(--text);}}.tab-btn.active{{color:var(--accent);border-bottom-color:var(--accent);}}
.meta{{font-family:var(--mono);font-size:10px;color:var(--text3);border:1px solid var(--border2);padding:3px 8px;border-radius:3px;margin-left:auto;white-space:nowrap;}}
.panel{{display:none;padding:32px;min-height:calc(100vh - 54px);max-width:1600px;margin:0 auto;}}.panel.active{{display:block;}}
.kpi-strip{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:1px;background:var(--border);border:1px solid var(--border);border-radius:10px;overflow:hidden;margin-bottom:20px;box-shadow:0 1px 5px rgba(0,0,0,.06);}}
.kpi-card{{background:var(--bg2);padding:18px 22px;}}
.kpi-label{{font-size:9px;color:var(--text3);text-transform:uppercase;letter-spacing:.1em;margin-bottom:6px;font-family:var(--mono);}}
.kpi-value{{font-family:var(--mono);font-size:20px;font-weight:700;color:var(--text);}}
.kpi-sub{{font-size:11px;color:var(--text2);margin-top:3px;}}
.kpi-green{{color:var(--green);}}.kpi-amber{{color:var(--amber);}}.kpi-red{{color:var(--red);}}
.week-btn{{padding:6px 16px;border-radius:4px;font-size:11.5px;cursor:pointer;border:1px solid var(--border2);background:var(--bg2);color:var(--text2);font-family:var(--mono);font-weight:600;transition:all .12s;}}
.week-btn:hover{{color:var(--text);border-color:var(--accent);}}.week-btn.active{{background:var(--accent);color:#fff;border-color:var(--accent);}}
.chart-card{{background:var(--bg2);border:1px solid var(--border);border-radius:10px;padding:20px;box-shadow:0 1px 5px rgba(0,0,0,.06);}}
.table-wrap{{overflow-x:auto;border-radius:10px;border:1px solid var(--border);box-shadow:0 1px 5px rgba(0,0,0,.05);}}
table{{width:100%;border-collapse:collapse;min-width:600px;}}
thead th{{background:var(--bg3);color:var(--text3);font-size:9px;text-transform:uppercase;letter-spacing:.1em;padding:7px 10px;text-align:right;white-space:nowrap;border-bottom:1px solid var(--border);font-family:var(--mono);font-weight:600;}}
thead th:first-child{{text-align:left;}}
tbody tr{{border-bottom:1px solid var(--border);}}
tbody tr:last-child{{border-bottom:none;}}
tbody tr:hover{{background:rgba(15,23,42,.025);}}
tbody td{{padding:6px 10px;text-align:right;font-family:var(--mono);font-size:11.5px;vertical-align:middle;}}
tbody td:first-child{{text-align:left;font-family:var(--body);font-size:13px;}}
.asin-link{{color:var(--accent);text-decoration:none;font-family:var(--mono);font-size:10px;}}
.asin-link:hover{{text-decoration:underline;}}
.week-group th{{background:var(--bg2);color:var(--text2);font-size:9px;}}
.muted{{color:var(--text3);}}
.sec-header{{font-family:var(--display);font-size:13px;font-weight:700;color:var(--text2);letter-spacing:.04em;text-transform:uppercase;padding:16px 0 10px;border-bottom:1px solid var(--border);margin-bottom:12px;}}
.tacos-ok{{color:var(--green);}}.tacos-warn{{color:var(--amber);}}.tacos-bad{{color:var(--red);}}
/* Parent row toggle */
.parent-row{{cursor:pointer;user-select:none;}}
.parent-row:hover td{{background:rgba(15,23,42,.03);}}
.toggle-icon{{display:inline-block;width:14px;transition:transform .15s;}}
.child-rows{{}}.child-rows.collapsed tr{{display:none;}}
/* Action cards */
.action-card{{background:var(--bg2);border:1px solid var(--border);border-radius:10px;padding:20px;margin-bottom:12px;box-shadow:0 1px 4px rgba(0,0,0,.05);}}
.action-card-header{{display:flex;align-items:center;gap:12px;margin-bottom:14px;}}
.action-card-title{{font-family:var(--display);font-size:16px;font-weight:700;}}
.action-card-badge{{font-size:9px;font-family:var(--mono);padding:3px 8px;border-radius:3px;font-weight:600;}}
.badge-star{{background:rgba(22,163,74,.12);color:var(--green);border:1px solid rgba(31,219,138,.3);}}
.badge-question{{background:rgba(217,119,6,.1);color:var(--amber);border:1px solid rgba(245,166,35,.3);}}
.badge-cut{{background:rgba(220,38,38,.1);color:var(--red);border:1px solid rgba(240,75,75,.3);}}
.badge-potential{{background:rgba(37,99,235,.1);color:var(--accent);border:1px solid rgba(91,138,240,.3);}}
.badge-now{{background:rgba(220,38,38,.1);color:var(--red);border:1px solid rgba(240,75,75,.3);}}
.badge-next{{background:rgba(37,99,235,.1);color:var(--accent);border:1px solid rgba(91,138,240,.3);}}
.action-tasks{{display:flex;flex-direction:column;gap:8px;}}
.action-task{{display:flex;align-items:flex-start;gap:10px;padding:10px 12px;background:var(--bg3);border-radius:6px;border:1px solid var(--border);}}
.action-task input[type=checkbox]{{margin-top:2px;accent-color:var(--accent);width:14px;height:14px;flex-shrink:0;}}
.action-task.done{{opacity:.35;}}
.action-task.done .task-text{{text-decoration:line-through;}}
.task-text{{font-size:12.5px;color:var(--text2);line-height:1.5;}}
.task-type{{font-family:var(--mono);font-size:9px;padding:1px 5px;border-radius:2px;background:var(--bg);color:var(--text3);border:1px solid var(--border2);flex-shrink:0;margin-top:2px;}}
.q-card{{background:var(--bg2);border:1px solid var(--border);border-radius:8px;padding:16px;}}
.q-card-title{{font-family:var(--display);font-size:13px;font-weight:700;margin-bottom:8px;}}
.q-card-body{{font-size:11px;color:var(--text2);line-height:1.7;}}
.done-cb{{cursor:pointer;accent-color:var(--accent);width:14px;height:14px;}}
tr.done-row td{{opacity:.35;text-decoration:line-through;}}
/* View mode toggle */
.view-toggle{{display:inline-flex;border:1px solid var(--border2);border-radius:6px;overflow:hidden;margin-right:12px;}}
.view-toggle-btn{{padding:6px 14px;font-size:11px;font-family:var(--mono);font-weight:600;cursor:pointer;border:none;background:var(--bg2);color:var(--text3);transition:all .12s;}}
.view-toggle-btn:not(:last-child){{border-right:1px solid var(--border2);}}
.view-toggle-btn:hover{{color:var(--text);}}
.view-toggle-btn.active{{background:var(--accent);color:#fff;}}
.month-btn{{padding:8px 20px;border-radius:6px;font-size:12.5px;cursor:pointer;border:1px solid var(--border2);background:var(--bg2);color:var(--text2);font-family:var(--mono);font-weight:700;transition:all .12s;}}
.month-btn:hover{{color:var(--text);border-color:var(--accent);}}
.month-btn.active{{background:var(--accent);color:#fff;border-color:var(--accent);}}
.period-bar{{display:flex;align-items:center;gap:8px;margin-bottom:16px;flex-wrap:wrap;}}

/* childTable freeze pane */
#childTable-wrap{{max-height:calc(100vh - 160px);overflow:auto;border-radius:10px;border:1px solid var(--border);box-shadow:0 1px 5px rgba(0,0,0,.05);}}
#childTable thead tr:nth-child(1) th{{position:sticky;top:0;z-index:4;background:var(--bg3);}}
#childTable thead tr:nth-child(2) th{{position:sticky;z-index:3;background:var(--bg2);}}
#childTable thead tr:nth-child(1) th.col-freeze{{z-index:6;}}
#childTable thead tr:nth-child(2) th.col-freeze{{z-index:5;}}
#childTable th.col-freeze,#childTable td.col-freeze{{position:sticky;left:0;z-index:2;box-shadow:2px 0 4px -1px rgba(0,0,0,.08);}}
#childTable tbody td.col-freeze{{background:var(--bg2);}}
#childTable .parent-row td.col-freeze{{background:inherit;}}
#childTable tfoot td.col-freeze{{background:var(--bg3);}}
</style>
</head>
<body>
<nav>
  <div class="nav-inner">
  <div class="nav-brand">Brain Tea <span class="market-tag">US</span></div>
  <div class="tabs">
    <button class="tab-btn active" onclick="showTab('t1',this)">&#x1F4CA; 銷售 &amp; 廣告佔比</button>
    <button class="tab-btn" onclick="showTab('t2',this)">&#x1F4C5; 週對週數據</button>
    <button class="tab-btn" onclick="showTab('t3',this)">&#x1F4C8; WoW 變化</button>
    <button class="tab-btn" onclick="showTab('t4',this)">&#x1F3AF; 產品象限</button>
    <button class="tab-btn" onclick="showTab('t5',this)">&#x2705; 行動方案</button>
  </div>
  <div class="meta">Feb–Mar 2026 · 週/月切換 · SP+SB · TACOS ≤15%</div>
  </div>
</nav>

<!-- TAB 1 -->
<div id="t1" class="panel active">
  <div style="margin-bottom:16px">
    <div style="font-size:10px;color:var(--text3);letter-spacing:.1em;text-transform:uppercase;margin-bottom:4px;font-family:var(--mono)">全產品線佔比分析 · US Market</div>
    <div style="font-size:28px;font-weight:800;color:var(--accent);font-family:var(--display);margin-bottom:4px">Sales &amp; Ad Spend — Feb–Mar 2026</div>
    <div style="font-size:11px;color:var(--text3)">數據來源：ScaleInsight · 目標 TACOS ≤ 15% · SP+SB 合計</div>
  </div>
  <div class="period-bar">
    <div class="view-toggle">
      <button class="view-toggle-btn active" onclick="setViewMode('week',this)">週 Weeks</button>
      <button class="view-toggle-btn" onclick="setViewMode('month',this)">月 Months</button>
    </div>
    <div id="periodBtns"></div>
  </div>
  <div class="kpi-strip" id="kpi-t1"></div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px">
    <div class="chart-card">
      <div style="font-size:13px;font-weight:600;margin-bottom:4px">產品營業額佔比</div>
      <div style="font-size:10px;color:var(--text3);margin-bottom:14px;font-family:var(--mono)">SALES DISTRIBUTION</div>
      <div style="display:flex;gap:20px;align-items:flex-start">
        <div style="flex-shrink:0;position:relative">
          <canvas id="salesPie" width="160" height="160"></canvas>
          <div style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);text-align:center;pointer-events:none">
            <div style="font-family:var(--mono);font-size:11px;font-weight:700;color:var(--text)" id="salesTotalLbl"></div>
            <div style="font-size:8px;color:var(--text3)">TOTAL</div>
          </div>
        </div>
        <div id="salesList" style="flex:1;display:flex;flex-direction:column;gap:0;overflow-y:auto;max-height:220px"></div>
      </div>
    </div>
    <div class="chart-card">
      <div style="font-size:13px;font-weight:600;margin-bottom:4px">廣告花費佔比</div>
      <div style="font-size:10px;color:var(--text3);margin-bottom:14px;font-family:var(--mono)">AD SPEND DISTRIBUTION</div>
      <div style="display:flex;gap:20px;align-items:flex-start">
        <div style="flex-shrink:0;position:relative">
          <canvas id="adsPie" width="160" height="160"></canvas>
          <div style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);text-align:center;pointer-events:none">
            <div style="font-family:var(--mono);font-size:11px;font-weight:700;color:var(--text)" id="adsTotalLbl"></div>
            <div style="font-size:8px;color:var(--text3)">AD SPEND</div>
          </div>
        </div>
        <div id="adsList" style="flex:1;display:flex;flex-direction:column;gap:0;overflow-y:auto;max-height:220px"></div>
      </div>
    </div>
  </div>
  <div class="sec-header">產品銷售明細 — 點擊產品名稱可展開 / 收合子變體</div>
  <div id="childTable-wrap"><table id="childTable"></table></div>
</div>

<!-- TAB 2 -->
<div id="t2" class="panel">
  <div class="kpi-strip" id="kpi-t2"></div>
  <div class="table-wrap"><table id="wowTable"></table></div>
</div>

<!-- TAB 3 -->
<div id="t3" class="panel">
  <div class="sec-header">Week-over-Week % 變化 — Sales · Spend · TACOS · Units</div>
  <div class="table-wrap"><table id="heatTable"></table></div>
</div>

<!-- TAB 4 -->
<div id="t4" class="panel">
  <div class="kpi-strip" id="kpi-t4"></div>
  <div style="display:grid;grid-template-columns:auto 1fr;gap:16px;margin-bottom:20px;align-items:start">
    <div class="chart-card" style="padding:16px">
      <canvas id="quadCanvas" width="640" height="480"></canvas>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px" id="qCards"></div>
  </div>
</div>

<!-- TAB 5 -->
<div id="t5" class="panel">
  <div style="margin-bottom:20px">
    <div style="font-size:28px;font-weight:800;color:var(--accent);font-family:var(--display);margin-bottom:4px">行動方案 Action Plan</div>
    <div style="font-size:11px;color:var(--text3)">依象限分類 · 勾選完成項目 · 對應 Bulk File 操作</div>
  </div>
  <div id="actionCards"></div>
</div>

<script>
const PARENTS = {parents_json};
const CHILD_DATA = {child_json};

const ZH = {zh_json};
const CHILD_ZH = {child_zh_json};

const TACOS_TARGET = {TACOS_TARGET};
const WEEKS = {json.dumps(WEEK_KEYS)};
const W_LABELS = {w_labels_json};
const MONTHS = {{
  "Feb": {{label:"Feb 2026", weeks:["W1","W2","W3","W4"]}},
  "Mar": {{label:"Mar 2026 (partial)", weeks:["W5"]}}
}};
const M_KEYS = Object.keys(MONTHS);

const $ = id => document.getElementById(id);
const fmt = (v,d=0) => v==null?'\\u2014':'$'+v.toLocaleString('en-US',{{minimumFractionDigits:d,maximumFractionDigits:d}});
const pct = v => v==null?'\\u2014':v.toFixed(1)+'%';
const tacosClass = v => v==null?'muted':v<=TACOS_TARGET?'tacos-ok':v<=TACOS_TARGET*1.67?'tacos-warn':'tacos-bad';
const zhName = pid => (ZH[pid]||'') + ' ' + (PARENTS[pid]?PARENTS[pid].short:'');
const zhShort = pid => ZH[pid] || (PARENTS[pid]?PARENTS[pid].short:'');

function showTab(id, btn) {{
  document.querySelectorAll('.panel').forEach(p=>p.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b=>b.classList.remove('active'));
  $(id).classList.add('active');
  if(btn) btn.classList.add('active');
}}

function sortedParents() {{
  return Object.entries(PARENTS).sort((a,b)=>b[1].total_sales-a[1].total_sales);
}}

function drawDonut(canvasId, data) {{
  const canvas=$(canvasId); if(!canvas) return;
  const ctx=canvas.getContext('2d');
  const W=canvas.width,H=canvas.height;
  ctx.clearRect(0,0,W,H);
  const cx=W/2,cy=H/2,r=W/2-8,ir=r*0.58;
  const sum=data.reduce((s,d)=>s+d.value,0); if(sum===0) return;
  let angle=-Math.PI/2;
  data.forEach(d=>{{
    const sweep=(d.value/sum)*Math.PI*2;
    ctx.beginPath();ctx.moveTo(cx,cy);ctx.arc(cx,cy,r,angle,angle+sweep);ctx.closePath();
    ctx.fillStyle=d.color;ctx.fill();angle+=sweep;
  }});
  ctx.beginPath();ctx.arc(cx,cy,ir,0,Math.PI*2);ctx.fillStyle='#ffffff';ctx.fill();
}}

// TAB 1
window._viewMode = 'week';
window._modeWeeksMap = {{}};

function buildT1() {{
  window._t1={{}};
  const allModes = ['all',...WEEKS,...M_KEYS,'month_all'];
  allModes.forEach(mode=>{{
    const sp=sortedParents();
    let weeks;
    if(mode==='all') weeks=WEEKS;
    else if(mode==='month_all') weeks=WEEKS;
    else if(MONTHS[mode]) weeks=MONTHS[mode].weeks;
    else weeks=[mode];
    window._modeWeeksMap[mode]=weeks;
    const byAsin=sp.map(([pid,p])=>{{
      const sales=weeks.reduce((a,w)=>a+p.weeks[w].sales,0);
      const spend=weeks.reduce((a,w)=>a+p.weeks[w].spend,0);
      const spsd =weeks.reduce((a,w)=>a+p.weeks[w].spsd,0);
      const units=weeks.reduce((a,w)=>a+p.weeks[w].units,0);
      const tacos=sales>0?spend/sales*100:null;
      return {{pid,name:p.name,short:zhShort(pid),color:p.color,sales,spend,spsd,units,tacos,children:p.children}};
    }}).sort((a,b)=>b.sales-a.sales);
    window._t1[mode]={{
      byAsin,
      totSales: byAsin.reduce((s,p)=>s+p.sales,0),
      totSpend: byAsin.reduce((s,p)=>s+p.spend,0),
      totUnits: byAsin.reduce((s,p)=>s+p.units,0),
      totProfit:sp.reduce((s,[,p])=>s+weeks.reduce((a,w)=>a+p.weeks[w].profits,0),0),
    }};
  }});
  setViewMode('week', document.querySelector('.view-toggle-btn'));
}}

function setViewMode(mode, btn) {{
  window._viewMode = mode;
  document.querySelectorAll('.view-toggle-btn').forEach(b=>b.classList.remove('active'));
  if(btn) btn.classList.add('active');

  const container = $('periodBtns');
  if(mode==='week') {{
    container.innerHTML = `
      <div style="display:flex;gap:6px;flex-wrap:wrap">
        <button class="week-btn active" onclick="switchWeek('all',this)">5W 合計 All</button>
        ${{WEEKS.map(w=>`<button class="week-btn" onclick="switchWeek('${{w}}',this)">${{w}} ${{W_LABELS[w]}}</button>`).join('')}}
      </div>`;
    switchWeek('all', container.querySelector('.week-btn'));
  }} else {{
    container.innerHTML = `
      <div style="display:flex;gap:8px;flex-wrap:wrap">
        <button class="month-btn active" onclick="switchWeek('month_all',this)">全期間 All</button>
        ${{M_KEYS.map(m=>`<button class="month-btn" onclick="switchWeek('${{m}}',this)">${{MONTHS[m].label}}</button>`).join('')}}
      </div>`;
    switchWeek('month_all', container.querySelector('.month-btn'));
  }}
}}

function switchWeek(mode, btn) {{
  document.querySelectorAll('.week-btn,.month-btn').forEach(b=>b.classList.remove('active'));
  if(btn) btn.classList.add('active');
  const d=window._t1[mode]; if(!d) return;

  const tClass=v=>v==null?'':v<=TACOS_TARGET?'kpi-green':v<=TACOS_TARGET*1.67?'kpi-amber':'kpi-red';
  const acctTacos=d.totSales>0?d.totSpend/d.totSales*100:0;
  const top=d.byAsin[0];
  const topSpend=[...d.byAsin].filter(p=>p.spend>0).sort((a,b)=>b.spend-a.spend)[0];
  $('kpi-t1').innerHTML=`
    <div class="kpi-card"><div class="kpi-label">Total Sales</div><div class="kpi-value">${{fmt(d.totSales,0)}}</div><div class="kpi-sub">${{d.totUnits}} units</div></div>
    <div class="kpi-card"><div class="kpi-label">Total Ad Spend</div><div class="kpi-value kpi-amber">${{fmt(d.totSpend,0)}}</div><div class="kpi-sub">SP+SB</div></div>
    <div class="kpi-card"><div class="kpi-label">Account TACOS</div><div class="kpi-value ${{tClass(acctTacos)}}">${{pct(acctTacos)}}</div><div class="kpi-sub">${{acctTacos<=TACOS_TARGET?'\\u2713 On Target':'\\u26A0 Above 15%'}}</div></div>
    <div class="kpi-card"><div class="kpi-label">Total Profit</div><div class="kpi-value ${{d.totProfit>=0?'kpi-green':'kpi-red'}}">${{fmt(d.totProfit,0)}}</div><div class="kpi-sub">${{d.totProfit>=0?'\\u25B2 盈利':'\\u25BC 虧損'}}</div></div>
    <div class="kpi-card"><div class="kpi-label">銷售最大</div><div class="kpi-value" style="font-size:14px">${{top?top.short:'\\u2014'}}</div><div class="kpi-sub" style="color:var(--green)">${{top?fmt(top.sales,0):''}}</div></div>
    <div class="kpi-card"><div class="kpi-label">廣告最燒</div><div class="kpi-value" style="font-size:14px">${{topSpend?topSpend.short:'\\u2014'}}</div><div class="kpi-sub" style="color:var(--amber)">${{topSpend?fmt(topSpend.spend,0)+' \\u00B7 '+pct(topSpend.tacos):''}}</div></div>`;

  const salesData=d.byAsin.filter(p=>p.sales>0).map(p=>({{value:p.sales,color:p.color}}));
  drawDonut('salesPie',salesData);
  $('salesTotalLbl').textContent=fmt(d.totSales,0);
  $('salesList').innerHTML=d.byAsin.filter(p=>p.sales>0).map(p=>{{
    const p2=d.totSales>0?(p.sales/d.totSales*100).toFixed(1):'0.0';
    return `<div style="display:flex;align-items:center;gap:6px;padding:3px 0;border-bottom:1px solid var(--border)">
      <span style="width:8px;height:8px;border-radius:50%;background:${{p.color}};flex-shrink:0"></span>
      <span style="flex:1;font-size:12px;color:var(--text2)">${{p.short}}</span>
      <span style="font-family:var(--mono);font-size:11px;font-weight:700;color:var(--text)">${{p2}}%</span>
      <span style="font-family:var(--mono);font-size:11px;color:var(--text3);min-width:54px;text-align:right">${{fmt(p.sales,0)}}</span>
    </div>`;
  }}).join('');

  const spendData=d.byAsin.filter(p=>p.spend>0).sort((a,b)=>b.spend-a.spend).map(p=>({{value:p.spend,color:p.color}}));
  drawDonut('adsPie',spendData);
  $('adsTotalLbl').textContent=fmt(d.totSpend,0);
  $('adsList').innerHTML=d.byAsin.filter(p=>p.spend>0).sort((a,b)=>b.spend-a.spend).map(p=>{{
    const p2=d.totSpend>0?(p.spend/d.totSpend*100).toFixed(1):'0.0';
    const over=p.sales>0&&parseFloat(p2)>(d.totSales>0?p.sales/d.totSales*100:0)*1.5&&parseFloat(p2)>3;
    return `<div style="display:flex;align-items:center;gap:6px;padding:3px 0;border-bottom:1px solid var(--border)${{over?';background:rgba(220,38,38,.04)':''}}">
      <span style="width:8px;height:8px;border-radius:50%;background:${{p.color}};flex-shrink:0"></span>
      <span style="flex:1;font-size:12px;color:var(--text2)">${{p.short}}${{over?' <span style="color:var(--red);font-size:9px">\\u26A0廣告過重</span>':''}}</span>
      <span style="font-family:var(--mono);font-size:11px;font-weight:700;color:${{over?'var(--red)':'var(--text)'}}">${{p2}}%</span>
      <span style="font-family:var(--mono);font-size:11px;color:var(--text3);min-width:54px;text-align:right">${{fmt(p.spend,0)}}</span>
    </div>`;
  }}).join('');

  renderChildTable(mode);
}}

function renderChildTable(mode) {{
  const tbl=$('childTable'); if(!tbl) return;

  let cols;
  if(mode==='month_all') {{
    cols = M_KEYS.map(m=>({{key:m, label:MONTHS[m].label, weeks:MONTHS[m].weeks}}));
  }} else if(MONTHS[mode]) {{
    cols = MONTHS[mode].weeks.map(w=>({{key:w, label:w+' '+W_LABELS[w], weeks:[w]}}));
  }} else if(mode==='all') {{
    cols = WEEKS.map(w=>({{key:w, label:w+' '+W_LABELS[w], weeks:[w]}}));
  }} else {{
    cols = [{{key:mode, label:mode+' '+W_LABELS[mode], weeks:[mode]}}];
  }}

  const allWeeks = cols.flatMap(c=>c.weeks);
  const modeAdj=CHILD_DATA.reduce((s,r)=>s+allWeeks.reduce((a,w)=>a+r.weeks[w].sales,0),0);

  const wH=cols.map(c=>`<th colspan="3" style="text-align:center;border-left:1px solid var(--border2)">${{c.label}}</th>`).join('');
  const sH=cols.map(()=>`<th style="border-left:1px solid var(--border2)">Sales</th><th>Spend</th><th>TACOS</th>`).join('');

  const parentIds=[...new Set(CHILD_DATA.map(r=>r.parent))];
  const parentOrder=sortedParents().map(([pid])=>pid).filter(pid=>parentIds.includes(pid));

  let bodyHtml='';
  let pIdx=0;
  parentOrder.forEach(pid=>{{
    const children=CHILD_DATA.filter(r=>r.parent===pid&&(allWeeks.reduce((a,w)=>a+r.weeks[w].sales,0)>0||allWeeks.reduce((a,w)=>a+r.weeks[w].spend,0)>0));
    if(!children.length) return;
    const p=PARENTS[pid];
    const pSales=children.reduce((s,r)=>s+allWeeks.reduce((a,w)=>a+r.weeks[w].sales,0),0);
    const pSpend=children.reduce((s,r)=>s+allWeeks.reduce((a,w)=>a+r.weeks[w].spend,0),0);
    const pTacos=pSales>0?pSpend/pSales*100:null;
    const pPct=modeAdj>0?(pSales/modeAdj*100).toFixed(1):'0.0';
    const gid=`pg${{pIdx++}}`;

    const pWcells=cols.map(c=>{{
      const wS=children.reduce((s,r)=>s+c.weeks.reduce((a,w)=>a+r.weeks[w].sales,0),0);
      const wE=children.reduce((s,r)=>s+c.weeks.reduce((a,w)=>a+r.weeks[w].spend,0),0);
      const tc=wS>0?wE/wS*100:null;
      return `<td style="border-left:1px solid var(--border2);font-weight:600">${{wS>0?fmt(wS,0):'\\u2014'}}</td>
              <td style="font-weight:600">${{wE>0?fmt(wE,0):'\\u2014'}}</td>
              <td class="${{tacosClass(tc)}}" style="font-weight:600">${{tc!=null?pct(tc):'\\u2014'}}</td>`;
    }}).join('');

    bodyHtml+=`<tr class="parent-row" onclick="toggleGroup('${{gid}}')" style="background:${{p.color}}0d;border-top:2px solid ${{p.color}}33">
      <td class="col-freeze">
        <span class="toggle-icon" id="ti_${{gid}}">\\u25BC</span>
        <span style="color:${{p.color}};font-weight:700;font-family:var(--display);font-size:13px;margin-left:4px">${{zhShort(pid)}}</span>
        <span style="color:var(--text3);font-size:10px;margin-left:8px;font-family:var(--mono)">${{children.length}} 個變體</span>
      </td>
      <td style="font-family:var(--mono);font-size:12px;color:var(--green);font-weight:700">${{pPct}}%</td>
      ${{pWcells}}
    </tr>`;

    bodyHtml+=`<tbody id="${{gid}}" class="child-rows">`;
    children.sort((a,b)=>b.total_sales-a.total_sales).forEach(r=>{{
      const cSales=allWeeks.reduce((a,w)=>a+r.weeks[w].sales,0);
      const cSpend=allWeeks.reduce((a,w)=>a+r.weeks[w].spend,0);
      const cPct=modeAdj>0?(cSales/modeAdj*100).toFixed(1):'0.0';
      const cName=CHILD_ZH[r.asin]||r.name.substring(0,50);
      const wCells=cols.map(c=>{{
        const cS=c.weeks.reduce((a,w)=>a+r.weeks[w].sales,0);
        const cE=c.weeks.reduce((a,w)=>a+r.weeks[w].spend,0);
        const tc=cS>0?cE/cS*100:null;
        return `<td style="border-left:1px solid var(--border2)">${{cS>0?fmt(cS,0):'\\u2014'}}</td>
                <td>${{cE>0?fmt(cE,0):'\\u2014'}}</td>
                <td class="${{tacosClass(tc)}}">${{tc!=null?pct(tc):'\\u2014'}}</td>`;
      }}).join('');
      bodyHtml+=`<tr style="background:var(--bg)">
        <td style="padding-left:32px">
          <a class="asin-link" href="https://www.amazon.com/dp/${{r.asin}}" target="_blank">${{r.asin}}</a>
          <span style="color:var(--text2);font-size:11.5px;margin-left:8px">${{cName}}</span>
        </td>
        <td style="font-family:var(--mono);font-size:11px;color:var(--text3)">${{cPct}}%</td>
        ${{wCells}}
      </tr>`;
    }});
    bodyHtml+='</tbody>';
  }});

  const totalCells=cols.map(c=>{{
    const wS=CHILD_DATA.reduce((s,r)=>s+c.weeks.reduce((a,w)=>a+r.weeks[w].sales,0),0);
    const wE=CHILD_DATA.reduce((s,r)=>s+c.weeks.reduce((a,w)=>a+r.weeks[w].spend,0),0);
    const wT=wS>0?wE/wS*100:null;
    return `<td style="border-left:1px solid var(--border2);font-weight:700">${{fmt(wS,0)}}</td>
            <td style="font-weight:700">${{fmt(wE,0)}}</td>
            <td class="${{tacosClass(wT)}}">${{wT!=null?pct(wT):'\\u2014'}}</td>`;
  }}).join('');

  const nWeeks=cols.length;
  const colDefs=[220,58,...Array(nWeeks*3).fill(0).flatMap((_,i)=>i%3===0?[82]:i%3===1?[72]:[60])];
  const cg='<colgroup>'+colDefs.map(w=>`<col style="width:${{w}}px">`).join('')+'</colgroup>';
  tbl.innerHTML=`${{cg}}<thead>
    <tr><th style="min-width:300px">產品 / 變體</th><th>Sales %</th>${{wH}}</tr>
    <tr class="week-group"><th></th><th></th>${{sH}}</tr>
  </thead>
  <tbody>${{bodyHtml}}</tbody>
  <tfoot><tr style="background:var(--bg3);font-weight:700;border-top:2px solid var(--border2)">
    <td>TOTAL</td><td>100%</td>${{totalCells}}
  </tr></tfoot>`;
  tbl.style.tableLayout='fixed';
  tbl.style.width='auto';
  requestAnimationFrame(()=>{{
    const rows=tbl.querySelectorAll('thead tr');
    if(rows[0]&&rows[1]){{
      const h=rows[0].getBoundingClientRect().height;
      rows[1].querySelectorAll('th').forEach(th=>th.style.top=h+'px');
    }}
  }});
}}

function toggleGroup(gid) {{
  const el=document.getElementById(gid);
  const icon=document.getElementById('ti_'+gid);
  if(!el) return;
  el.classList.toggle('collapsed');
  if(icon) icon.textContent=el.classList.contains('collapsed')?'\\u25B6':'\\u25BC';
}}

// TAB 2
function buildWowTab() {{
  const sp=sortedParents();
  const totals={{}};
  WEEKS.forEach(w=>totals[w]={{sales:0,spend:0,units:0,organic:0,ppc:0}});
  sp.forEach(([,p])=>WEEKS.forEach(w=>{{
    totals[w].sales+=p.weeks[w].sales;totals[w].spend+=p.weeks[w].spend;
    totals[w].units+=p.weeks[w].units;totals[w].organic+=p.weeks[w].organic;
  }}));
  $('kpi-t2').innerHTML=WEEKS.map(w=>{{
    const tc=totals[w].sales>0?totals[w].spend/totals[w].sales*100:0;
    return `<div class="kpi-card"><div class="kpi-label">${{w}} \\u00B7 ${{W_LABELS[w]}}</div>
      <div class="kpi-value" style="font-size:18px">${{fmt(totals[w].sales,0)}}</div>
      <div class="kpi-sub">Spend ${{fmt(totals[w].spend,0)}} \\u00B7 TACOS <span class="${{tacosClass(tc)}}">${{pct(tc)}}</span></div>
    </div>`;
  }}).join('');
  $('wowTable').innerHTML=`<thead><tr><th rowspan="2">產品</th>
    ${{WEEKS.map(w=>`<th colspan="5" style="text-align:center;background:var(--bg3)">${{w}} ${{W_LABELS[w]}}</th>`).join('')}}</tr>
    <tr class="week-group">${{WEEKS.map(()=>'<th>Sales</th><th>Spend</th><th>TACOS</th><th>Units</th><th>Organic</th>').join('')}}</tr>
  </thead><tbody>${{sp.map(([pid,p])=>`<tr>
    <td><span style="display:inline-block;width:8px;height:8px;background:${{p.color}};border-radius:2px;margin-right:6px"></span>
    <strong style="color:${{p.color}}">${{zhShort(pid)}}</strong><br>
    <span class="muted" style="font-size:10px">${{p.children.map(c=>`<a class="asin-link" href="https://www.amazon.com/dp/${{c}}" target="_blank">${{c}}</a>`).join(' ')}}</span></td>
    ${{WEEKS.map(w=>{{const wd=p.weeks[w],tc=wd.tacos;
      return `<td>${{fmt(wd.sales,0)}}</td><td>${{fmt(wd.spend,0)}}</td><td class="${{tacosClass(tc)}}">${{pct(tc)}}</td><td>${{wd.units||'\\u2014'}}</td><td>${{wd.organic||'\\u2014'}}`;
    }}).join('')}}
  </tr>`).join('')}}
  <tr style="background:var(--bg3);font-weight:700"><td>TOTAL</td>
    ${{WEEKS.map(w=>{{const tc=totals[w].sales>0?totals[w].spend/totals[w].sales*100:0;
      return `<td>${{fmt(totals[w].sales,0)}}</td><td>${{fmt(totals[w].spend,0)}}</td><td class="${{tacosClass(tc)}}">${{pct(tc)}}</td><td>${{totals[w].units}}</td><td>${{totals[w].organic}}</td>`;
    }}).join('')}}
  </tr></tbody>`;
}}

// TAB 3
function buildHeatTab() {{
  const sp=sortedParents();
  const periods=[['W1','W2'],['W2','W3'],['W3','W4'],['W4','W5']];
  const metrics=[{{key:'sales',label:'Sales',up:true}},{{key:'spend',label:'Spend',up:false}},{{key:'tacos',label:'TACOS',up:false}},{{key:'units',label:'Units',up:true}}];
  const chg=(a,b)=>(!a||a===0)?null:(b-a)/a*100;
  const fmtC=(v,up)=>{{if(v==null)return'<span class="muted">\\u2014</span>';const g=(up?v>0:v<0);return`<span style="color:${{g?'var(--green)':'var(--red)'}}">${{v>0?'+':''}}${{v.toFixed(1)}}%</span>`;}};
  const wH=periods.map(([a,b])=>metrics.map(m=>`<th>${{a}}\\u2192${{b}}<br><span style="color:var(--text2);font-weight:400">${{m.label}}</span></th>`).join('')).join('');
  $('heatTable').innerHTML=`<thead><tr><th>產品</th>${{wH}}</tr></thead><tbody>${{
    sp.map(([pid,p])=>`<tr><td><span style="display:inline-block;width:8px;height:8px;background:${{p.color}};border-radius:2px;margin-right:6px"></span>${{zhShort(pid)}}</td>
      ${{periods.map(([a,b])=>metrics.map(m=>`<td>${{fmtC(chg(p.weeks[a][m.key],p.weeks[b][m.key]),m.up)}}</td>`).join('')).join('')}}
    </tr>`).join('')
  }}</tbody>`;
}}

// TAB 4 — QUADRANT
function getQuadrant(p, med) {{
  if(p.total_sales>=med && p.tacos_4w<=TACOS_TARGET) return 'star';
  if(p.total_sales>=med && p.tacos_4w>TACOS_TARGET)  return 'question';
  if(p.total_sales<med  && p.tacos_4w<=TACOS_TARGET)  return 'potential';
  return 'cut';
}}

function buildQuadTab() {{
  const sp=sortedParents().filter(([,p])=>p.total_sales>0);
  const salesArr=sp.map(([,p])=>p.total_sales).sort((a,b)=>a-b);
  const med=salesArr.length%2===0?(salesArr[salesArr.length/2-1]+salesArr[salesArr.length/2])/2:salesArr[Math.floor(salesArr.length/2)];
  const totS=sp.reduce((s,[,p])=>s+p.total_sales,0);
  const totE=sp.reduce((s,[,p])=>s+p.total_spend,0);
  const acct=totS>0?totE/totS*100:0;
  const qStar=sp.filter(([,p])=>getQuadrant(p,med)==='star');
  const qQuestion=sp.filter(([,p])=>getQuadrant(p,med)==='question');
  const qPotential=sp.filter(([,p])=>getQuadrant(p,med)==='potential');
  const qCut=sp.filter(([,p])=>getQuadrant(p,med)==='cut');

  $('kpi-t4').innerHTML=`
    <div class="kpi-card"><div class="kpi-label">TACOS Target</div><div class="kpi-value kpi-green">15%</div><div class="kpi-sub">Y-axis threshold</div></div>
    <div class="kpi-card"><div class="kpi-label">Account TACOS</div><div class="kpi-value ${{acct<=15?'kpi-green':acct<=25?'kpi-amber':'kpi-red'}}">${{pct(acct)}}</div><div class="kpi-sub">SP+SB total</div></div>
    <div class="kpi-card"><div class="kpi-label">Sales Median</div><div class="kpi-value">${{fmt(med,0)}}</div><div class="kpi-sub">X-axis threshold</div></div>
    <div class="kpi-card"><div class="kpi-label">\\u2B50 Star</div><div class="kpi-value kpi-green">${{qStar.length}}</div></div>
    <div class="kpi-card"><div class="kpi-label">\\u26A0\\uFE0F Question</div><div class="kpi-value kpi-amber">${{qQuestion.length}}</div></div>
    <div class="kpi-card"><div class="kpi-label">\\uD83D\\uDCA4 Potential</div><div class="kpi-value" style="color:var(--accent)">${{qPotential.length}}</div></div>
    <div class="kpi-card"><div class="kpi-label">\\uD83D\\uDD34 Cut</div><div class="kpi-value kpi-red">${{qCut.length}}</div></div>`;

const qDefs=[
    {{title:'Cut',color:'#dc2626',items:qCut,action:'調降售價 $0.50\\n建立 Coupon 折扣\\n設定 Prime 限時特賣'}},
    {{title:'Question',color:'#d97706',items:qQuestion,action:'降低 CPC 出價至 $0.50\\u2013$1.00\\n暫停 TACOS \\u226525% 關鍵字'}},
    {{title:'Potential',color:'#059669',items:qPotential,action:'增加 SP / SB 廣告\\n使用低 CPC 出價 $0.50\\u2013$1.00\\n建立 Lookalike 受眾活動\\n相似 KW 根詞 · 競品 ASIN'}},
    {{title:'Star',color:'#16a34a',items:qStar,action:'複製現有 SP 活動\\n提高預算 30%'}},
  ];
  $('qCards').innerHTML=qDefs.map(q=>`<div class="q-card" style="border-color:${{q.color}}33"><div class="q-card-title" style="color:${{q.color}}">${{q.title}}</div><div class="q-card-body">${{q.action.split('\\n').join('<br>')}}
    <br><br>${{q.items.map(([pid,p])=>`<span style="display:inline-block;margin:2px 3px;padding:2px 8px;background:${{p.color}}22;border:1px solid ${{p.color}}44;border-radius:3px;font-size:10px;color:${{p.color}};font-family:var(--mono)">${{zhShort(pid)}}</span>`).join('')}}
    ${{q.items.length===0?'<span class="muted">None</span>':''}}</div>
  </div>`).join('');

  // Canvas
  const canvas=$('quadCanvas');
  const ctx=canvas.getContext('2d');
  const CW=canvas.width,CH=canvas.height;
  ctx.clearRect(0,0,CW,CH);
  const MX=CW/2,MY=CH/2;
  function drawBox(x,y,w,h,bg,title,subtitle,items,tc){{
    ctx.fillStyle=bg;ctx.fillRect(x+1,y+1,w-2,h-2);
    ctx.fillStyle=tc;ctx.font='bold 20px Inter,sans-serif';ctx.textAlign='left';
    ctx.fillText(title,x+18,y+34);
    ctx.fillStyle='#64748b';ctx.font='10px Outfit,sans-serif';
    const lines=subtitle.split('\\n');
    lines.forEach((l,i)=>ctx.fillText(l,x+18,y+54+i*15));
    let cx2=x+18,cy2=y+54+lines.length*15+18;
    ctx.font='bold 10px JetBrains Mono,monospace';
    items.forEach(([pid,p])=>{{
      const lbl=zhShort(pid);
      const tw=ctx.measureText(lbl).width+14;
      if(cx2+tw>x+w-10){{cx2=x+18;cy2+=20;}}
      ctx.fillStyle=p.color+'2a';
      ctx.beginPath();ctx.roundRect(cx2,cy2-13,tw,18,3);ctx.fill();
      ctx.fillStyle=p.color;ctx.fillText(lbl,cx2+7,cy2);
      cx2+=tw+5;
    }});
  }}
  drawBox(0,0,MX,MY,'rgba(220,38,38,.05)','Cut','調降售價 $0.50\\n建立 Coupon\\n設定 Prime 特賣',qCut,'#dc2626');
  drawBox(MX,0,MX,MY,'rgba(217,119,6,.05)','Question','降低 CPC $0.50\\u2013$1.00\\n暫停 \\u226525% TACOS KW',qQuestion,'#d97706');
  drawBox(0,MY,MX,MY,'rgba(5,150,105,.05)','Potential','增加 SP/SB · 低 CPC\\nLookalike 受眾 · 競品 ASIN',qPotential,'#059669');
  drawBox(MX,MY,MX,MY,'rgba(22,163,74,.05)','Star','複製 SP 活動\\n預算 +30%',qStar,'#16a34a');
  ctx.strokeStyle='#059669';ctx.lineWidth=1.5;
  ctx.beginPath();ctx.moveTo(MX,0);ctx.lineTo(MX,CH);ctx.stroke();
  ctx.beginPath();ctx.moveTo(0,MY);ctx.lineTo(CW,MY);ctx.stroke();
  ctx.fillStyle='#059669';ctx.font='bold 13px Inter,sans-serif';ctx.textAlign='center';
  ctx.fillText('Brain Tea US \\u00B7 Feb\\u2013Mar 2026',CW/2,18);
  ctx.fillStyle='#94a3b8';ctx.font='11px JetBrains Mono,monospace';ctx.textAlign='left';
  ctx.fillText('TACOS \\u2191',6,MY-8);
  ctx.fillStyle='#059669';ctx.font='bold 20px JetBrains Mono,monospace';ctx.textAlign='right';
  ctx.fillText('15',MX-8,MY-6);
  ctx.fillStyle='#64748b';ctx.font='12px JetBrains Mono,monospace';
  ctx.fillText('0',MX-8,CH-8);
  ctx.textAlign='right';ctx.fillText('Sales \\u2192',CW-6,CH-8);
  ctx.textAlign='left';ctx.fillStyle='#64748b';ctx.font='10px Outfit,sans-serif';
  ctx.fillText('Bid $0.50\\u2013$1.00',8,CH-8);

  window._quad_med = med;
}}

// TAB 5 — Action Plan
function buildActionTab() {{
  const sp=sortedParents().filter(([,p])=>p.total_sales>0);
  const salesArr=sp.map(([,p])=>p.total_sales).sort((a,b)=>a-b);
  const med=salesArr.length%2===0?(salesArr[salesArr.length/2-1]+salesArr[salesArr.length/2])/2:salesArr[Math.floor(salesArr.length/2)];

  const QUAD_CONFIG = {{
    star:     {{label:'\\u2B50 Star',badgeCls:'badge-star',   pri:'badge-now', priLabel:'本週執行',
      tasks:[
        {{type:'SP Bulk',text:'下載現有 SP 活動 Bulk File \\u2192 複製所有 Enabled campaigns \\u2192 新命名加 _COPY 後綴'}},
        {{type:'Budget',text:'全部 SP 活動預算 \\u00D7 1.3（+30%）\\u2192 上傳 Bulk File'}},
        {{type:'SB',text:'檢查是否有 SB Banner 廣告，若無則新建 SB Campaign 指向此產品'}},
        {{type:'Review',text:'維持現有策略，監控 TACOS 保持在 15% 以下'}},
      ]}},
    question: {{label:'\\u26A0\\uFE0F Question',badgeCls:'badge-question',pri:'badge-now', priLabel:'本週執行',
      tasks:[
        {{type:'CPC',text:'下載 SP 活動 Bulk File \\u2192 找出 ACOS \\u226525% 的關鍵字 \\u2192 Bid \\u00D7 0.8（降20%）'}},
        {{type:'Pause KW',text:'TACOS \\u226525% 且過去 14 天無轉換的關鍵字 \\u2192 狀態改為 Paused'}},
        {{type:'Budget',text:'SP 活動預算維持不變，待 TACOS 下降至 15% 再考慮增加'}},
        {{type:'Review',text:'檢查競品 listing 定價，評估是否需要調整售價提高轉換率'}},
      ]}},
    cut:      {{label:'\\uD83D\\uDD34 Cut',badgeCls:'badge-cut',    pri:'badge-now', priLabel:'本週執行',
      tasks:[
        {{type:'Price',text:'在 Seller Central 將售價下調 $0.50，觀察轉換率變化'}},
        {{type:'Coupon',text:'建立 Coupon 折扣（建議 5\\u201310%）\\u2192 提升搜尋結果曝光'}},
        {{type:'Deal',text:'申請 Prime Exclusive Discount 或 Lightning Deal（需提前 2 週申請）'}},
        {{type:'SP Bid',text:'下載 SP Bulk File \\u2192 全部 Keyword Bid 降至 $0.50\\u2013$1.00 範圍'}},
      ]}},
    potential:{{label:'\\uD83D\\uDCA4 Potential',badgeCls:'badge-potential',pri:'badge-next',priLabel:'下週執行',
      tasks:[
        {{type:'SP',text:'新建 SP Auto campaign，日預算 $10，CPC 出價 $0.50\\u2013$1.00，30天跑數據'}},
        {{type:'SB',text:'新建 SB Banner campaign，指向此產品 store page，CPC $0.50\\u2013$1.00'}},
        {{type:'SD',text:'新建 SD Audience campaign，目標 Competitor ASIN 的瀏覽受眾'}},
        {{type:'KW',text:'用現有暢銷產品的高轉換 KW 根詞，建立 SP Exact Match campaign'}},
      ]}},
  }};

  const html=sp.map(([pid,p])=>{{
    const q=getQuadrant(p, med);
    const cfg=QUAD_CONFIG[q];
    const taskHtml=cfg.tasks.map((t,i)=>`
      <div class="action-task" id="task_${{pid}}_${{i}}">
        <input type="checkbox" onchange="toggleTask('${{pid}}',${{i}},this)">
        <span class="task-type">${{t.type}}</span>
        <span class="task-text">${{t.text}}</span>
      </div>`).join('');
    return `<div class="action-card">
      <div class="action-card-header">
        <span style="width:12px;height:12px;border-radius:3px;background:${{p.color}};display:inline-block;flex-shrink:0"></span>
        <div class="action-card-title" style="color:${{p.color}}">${{zhShort(pid)}}</div>
        <span class="action-card-badge ${{cfg.badgeCls}}">${{cfg.label}}</span>
        <span class="action-card-badge ${{cfg.pri}}">${{cfg.priLabel}}</span>
        <span style="font-family:var(--mono);font-size:11px;color:var(--text3);margin-left:auto">5W Sales ${{fmt(p.total_sales,0)}} \\u00B7 TACOS <span class="${{tacosClass(p.tacos_4w)}}">${{pct(p.tacos_4w)}}</span></span>
        <span style="font-family:var(--mono);font-size:10px;color:var(--text3)">${{p.children.map(c=>`<a class="asin-link" href="https://www.amazon.com/dp/${{c}}" target="_blank">${{c}}</a>`).join(' ')}}</span>
      </div>
      <div class="action-tasks">${{taskHtml}}</div>
    </div>`;
  }}).join('');

  $('actionCards').innerHTML=html;
}}

function toggleTask(pid, idx, cb) {{
  const el=document.getElementById(`task_${{pid}}_${{idx}}`);
  if(el) el.classList.toggle('done', cb.checked);
}}

// INIT
buildT1();
buildWowTab();
buildHeatTab();
buildQuadTab();
buildActionTab();
</script>
</body>
</html>'''


if __name__ == "__main__":
    main()
