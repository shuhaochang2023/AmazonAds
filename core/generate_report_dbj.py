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

CLIENT_NAME   = "DBJ"
MARKET        = "US"
CURRENCY      = "$"           # "$" | "£" | "€" | "A$"
LOCALE        = "en-US"       # "en-US" | "en-GB" | "de-DE"
TACOS_TARGET  = 15            # % threshold for TACOS classification
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
INPUT_DIR    = Path("/Users/koda/amazon-autopilot/clients/dbj/input")
SOURCE_HTML  = INPUT_DIR / "DAIKEN_Dashboard_Feb2026.html"  # not used for DBJ
PRODUCTS_CSV = INPUT_DIR / "Products.csv"
SALES_CSV    = INPUT_DIR / "HistoricalAsinDateSales.csv"
SB_CSV       = INPUT_DIR / "SB_report.csv"
OUTPUT_DIR   = Path("/Users/koda/amazon-autopilot/output/dbj")
OUTPUT_HTML  = OUTPUT_DIR / "DBJ_US_Feb-Mar_2026.html"

# ── Frozen weeks (W1-W4 = preserved from SOURCE_HTML, NOT recomputed from CSV) ──
# Preserves the original SP/SD/SB breakdown that's verified in the base HTML.
# Weekly workflow: add new week to WEEK_RANGES + W_LABELS above; leave FROZEN_WEEKS unchanged.
FROZEN_WEEKS = []  # DBJ: all weeks computed from CSV

# ── Parent visual config (DAIKEN US — update for other clients) ───────────
PARENT_COLORS: dict[str, str] = {
    "B09XGY3FQ1": "#2563eb",   # Wire Shelving
    "B0FVFCYKGB": "#16a34a",   # Rolling Storage Cart
    "B0FVD69MYD": "#7c3aed",   # Rolling Laptop Stand A
    "B0FVD1Z92C": "#ea580c",   # Rolling Laptop Stand B
    "B0FVFCJXWB": "#0891b2",   # Bathroom Storage
    "B097V3JSWH": "#ca8a04",   # Clothing Dryer Rack
    "B0CTK9VRFR": "#be185d",   # Sweater Hangers
    "B0FV8XGQV4": "#dc2626",   # Double Rail Clothes Rack
    "B0FVF8DRZQ": "#059669",   # Laptop Stand C
    "B0FVFG8W4X": "#6366f1",   # Shoe Rack
    "B0FV8YD8DP": "#f59e0b",   # 3-Tier Rolling Cart
    "B09R3BLFDT": "#84cc16",   # Sweater Hangers B
    "B09JBVTY9T": "#14b8a6",   # Broom Holder
    "B09MRGLH3L": "#a78bfa",   # Shower Caddy
}
PARENT_SHORTS: dict[str, str] = {
    "B09XGY3FQ1": "Wire Shelving",
    "B0FVFCYKGB": "Storage Cart 10D",
    "B0FVD69MYD": "Laptop Stand A",
    "B0FVD1Z92C": "Laptop Stand B",
    "B0FVFCJXWB": "Bathroom Storage",
    "B097V3JSWH": "Dryer Rack",
    "B0CTK9VRFR": "Sweater Hangers",
    "B0FV8XGQV4": "Double Rail Rack",
    "B0FVF8DRZQ": "Laptop Stand C",
    "B0FVFG8W4X": "Shoe Rack",
    "B0FV8YD8DP": "3-Tier Cart",
    "B09R3BLFDT": "Padded Hangers",
    "B09JBVTY9T": "Broom Holder",
    "B09MRGLH3L": "Shower Caddy",
}
# Traditional Chinese display names (optional — leave empty string to use English)
ZH_PARENTS: dict[str, str] = {
    "B09XGY3FQ1": "Wire Shelving",
    "B0FVFCYKGB": "Storage Cart 10D",
    "B0FVD69MYD": "Laptop Stand A",
    "B0FVD1Z92C": "Laptop Stand B",
    "B0FVFCJXWB": "Bathroom Storage",
    "B097V3JSWH": "Dryer Rack",
    "B0CTK9VRFR": "Sweater Hangers",
    "B0FV8XGQV4": "Double Rail Rack",
    "B0FVF8DRZQ": "Laptop Stand C",
    "B0FVFG8W4X": "Shoe Rack",
    "B0FV8YD8DP": "3-Tier Cart",
    "B09R3BLFDT": "Padded Hangers",
    "B09JBVTY9T": "Broom Holder",
    "B09MRGLH3L": "Shower Caddy",
}
ZH_CHILDREN: dict[str, str] = {}  # DBJ uses English names

# ── VINE Deductions (per week, from transaction report — 100% rebate orders) ─
# Computed from vine_rebates.csv: orders where |rebate| >= product_charges * 95%
# Run the VINE parser script to update these values for new periods.
VINE_DEDUCTIONS: dict[str, float] = {
    "W1": 2558.40,
    "W2": 6557.99,
    "W3": 2990.61,
    "W4": 45.99,
    "W5": 0.00,
}

# ── Inventory Age data (from FBA Inventory Age report) ───────────────────
# Each entry: asin, name, available, age buckets, units_shipped_30, days_of_supply, inbound_qty
# Days of supply thresholds: ≤60=green, ≤120=yellow, >120=red
INVENTORY_DATA: list[dict] = [
    {"asin":"B097V3JSWH","name":"Clothing Dryer Rack","available":120,"age_0_30":0,"age_31_60":132,"age_61_90":0,"age_91_180":0,"age_181_plus":0,"units_shipped_30":22,"days_of_supply":119,"inbound_qty":0},
    {"asin":"B0FV8XGQV4","name":"Double Rail Clothes Rack","available":20,"age_0_30":6,"age_31_60":14,"age_61_90":0,"age_91_180":0,"age_181_plus":0,"units_shipped_30":30,"days_of_supply":28,"inbound_qty":0},
    {"asin":"B09QVW7J24","name":"Sweater Hangers (Blue)","available":0,"age_0_30":1,"age_31_60":0,"age_61_90":0,"age_91_180":0,"age_181_plus":0,"units_shipped_30":28,"days_of_supply":0,"inbound_qty":0},
    {"asin":"B094X854R4","name":"3-Tier Wire Shelving 14x24x30","available":48,"age_0_30":35,"age_31_60":13,"age_61_90":0,"age_91_180":0,"age_181_plus":0,"units_shipped_30":36,"days_of_supply":68,"inbound_qty":31},
    {"asin":"B091X2PXZP","name":"5-Tier Wire Shelving Unit","available":51,"age_0_30":0,"age_31_60":1,"age_61_90":21,"age_91_180":34,"age_181_plus":0,"units_shipped_30":5,"days_of_supply":214,"inbound_qty":0},
    {"asin":"B0FVF9GS2S","name":"Storage Cart 10D (White)","available":0,"age_0_30":1,"age_31_60":0,"age_61_90":0,"age_91_180":0,"age_181_plus":0,"units_shipped_30":29,"days_of_supply":27,"inbound_qty":36},
    {"asin":"B08M5G2LLT","name":"5-Tier Wire Shelving Heavy Duty","available":31,"age_0_30":14,"age_31_60":0,"age_61_90":18,"age_91_180":0,"age_181_plus":0,"units_shipped_30":10,"days_of_supply":107,"inbound_qty":2},
    {"asin":"B09Z58XKBP","name":"4-Tier Wire Shelving Unit","available":19,"age_0_30":0,"age_31_60":0,"age_61_90":14,"age_91_180":6,"age_181_plus":0,"units_shipped_30":12,"days_of_supply":90,"inbound_qty":20},
    {"asin":"B09MRGLH3L","name":"Shower Caddy Organizer","available":14,"age_0_30":0,"age_31_60":12,"age_61_90":0,"age_91_180":0,"age_181_plus":2,"units_shipped_30":1,"days_of_supply":315,"inbound_qty":0},
    {"asin":"B0FVD69MYD","name":"Rolling Laptop Desk (Tilt)","available":19,"age_0_30":6,"age_31_60":13,"age_61_90":0,"age_91_180":0,"age_181_plus":0,"units_shipped_30":31,"days_of_supply":34,"inbound_qty":0},
    {"asin":"B0FV8YD8DP","name":"3-Tier Rolling Cart Metal","available":28,"age_0_30":67,"age_31_60":11,"age_61_90":0,"age_91_180":0,"age_181_plus":0,"units_shipped_30":32,"days_of_supply":281,"inbound_qty":0},
    {"asin":"B0FV8XKYPM","name":"4-Tier Stackable Shoe Rack (Set2)","available":22,"age_0_30":26,"age_31_60":15,"age_61_90":0,"age_91_180":0,"age_181_plus":0,"units_shipped_30":26,"days_of_supply":56,"inbound_qty":0},
    {"asin":"B0FV8YQTLZ","name":"2-Tier Extendable Shoe Rack","available":48,"age_0_30":6,"age_31_60":35,"age_61_90":7,"age_91_180":0,"age_181_plus":0,"units_shipped_30":1,"days_of_supply":351,"inbound_qty":0},
    {"asin":"B0CTK9VRFR","name":"Sweater Hangers Padded Black","available":91,"age_0_30":11,"age_31_60":82,"age_61_90":0,"age_91_180":0,"age_181_plus":0,"units_shipped_30":31,"days_of_supply":81,"inbound_qty":0},
    {"asin":"B0FVFBZKSQ","name":"Storage Cart 10D Rainbow","available":0,"age_0_30":26,"age_31_60":8,"age_61_90":0,"age_91_180":0,"age_181_plus":0,"units_shipped_30":35,"days_of_supply":27,"inbound_qty":40},
    {"asin":"B0FVD1Z92C","name":"Rolling Laptop Desk (Sit-Stand)","available":21,"age_0_30":7,"age_31_60":14,"age_61_90":0,"age_91_180":0,"age_181_plus":0,"units_shipped_30":29,"days_of_supply":29,"inbound_qty":0},
    {"asin":"B08ZXJR1DP","name":"4-Tier Wire Shelving Heavy Duty","available":48,"age_0_30":46,"age_31_60":20,"age_61_90":0,"age_91_180":0,"age_181_plus":0,"units_shipped_30":19,"days_of_supply":85,"inbound_qty":0},
    {"asin":"B0FVFCJXWB","name":"Bathroom Storage Rack","available":19,"age_0_30":6,"age_31_60":13,"age_61_90":0,"age_91_180":0,"age_181_plus":0,"units_shipped_30":31,"days_of_supply":31,"inbound_qty":0},
    {"asin":"B09JBVTY9T","name":"Broom & Mop Holder","available":6,"age_0_30":0,"age_31_60":2,"age_61_90":8,"age_91_180":0,"age_181_plus":0,"units_shipped_30":17,"days_of_supply":71,"inbound_qty":20},
    {"asin":"B0FVF8DRZQ","name":"Rolling Laptop Desk Silver","available":21,"age_0_30":13,"age_31_60":14,"age_61_90":0,"age_91_180":0,"age_181_plus":0,"units_shipped_30":18,"days_of_supply":43,"inbound_qty":0},
    {"asin":"B09QW5PD83","name":"Sweater Hangers (Multi)","available":50,"age_0_30":25,"age_31_60":25,"age_61_90":3,"age_91_180":0,"age_181_plus":0,"units_shipped_30":21,"days_of_supply":77,"inbound_qty":24},
    {"asin":"B0FVFGJT63","name":"Storage Cart 10D Black","available":0,"age_0_30":20,"age_31_60":0,"age_61_90":0,"age_91_180":0,"age_181_plus":0,"units_shipped_30":27,"days_of_supply":46,"inbound_qty":36},
    {"asin":"B094XBLMGH","name":"3-Tier Wire Shelving 14x24x30 B","available":35,"age_0_30":11,"age_31_60":24,"age_61_90":0,"age_91_180":0,"age_181_plus":0,"units_shipped_30":29,"days_of_supply":89,"inbound_qty":24},
]

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
    sb_pool: dict = defaultdict(float)
    with open(path, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            d  = _parse_date(r.get("Date", ""))
            wk = _get_week(d) if d else None
            if not wk: continue
            a = r.get("ASIN", "").strip()
            if not a: continue
            sp = _pf(r.get("PPC Cost", 0))
            if "Sponsored Brands" in a:
                sb_pool[wk] += sp
                continue
            wd = weekly[a][wk]
            wd["sales"]   += _pf(r.get("Sales",           0))
            wd["spend"]   += sp
            wd["units"]   += int(_pf(r.get("Units",        0)))
            wd["organic"] += int(_pf(r.get("Organic Units",0)))
            wd["ppc"]     += int(_pf(r.get("PPC Orders",   0)))
            wd["profits"] += _pf(r.get("Profits",          0))
    return weekly, sb_pool

# ── Load SB Attributed Purchases report (Amazon Ads Console format) ──────────
# Columns used: Date, Purchased ASIN, "14 Day Total Sales "
# This report gives SB-attributed SALES (not spend).
# SB spend is in separate rows in HistoricalAsinDateSales, distributed in build_data().
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

    # Column name has a trailing space in Amazon's export — detect before loop
    with open(path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        SALES_COL = next(
            (k for k in reader.fieldnames or [] if "14 Day Total Sales" in k and "Click" not in k),
            "14 Day Total Sales "
        )
        rows_sb = list(reader)

    with open(path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for r in reader:
            d  = _parse_sb_date(r.get("Date", ""))
            wk = _get_week(d) if d else None
            if not wk: continue

            child = r.get("Purchased ASIN", "").strip()
            parent = child_to_parent.get(child, child)
            if parent not in PARENT_COLORS: continue  # DBJ: skip unknown parents
            sb[parent][wk]["sb_attr"] += _parse_money(r.get(SALES_COL, 0))
            # sbsp stays 0 — SB spend is in separate rows, distributed in build_data()

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
               sb_data: dict, sb_pool: dict, frozen_parents: dict, frozen_children: dict) -> tuple[dict, list]:

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

    # Pre-compute total SB attributed sales per week across ALL parents
    sb_attr_totals_by_week = {
        w: sum(sb_data.get(p, {}).get(w, {}).get("sb_attr", 0) for p in parent_children)
        for w in WEEKS
    }

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
            sb_attr_this  = sb_data.get(parent, {}).get(w, {}).get("sb_attr", 0)
            sb_attr_total = sum(sb_data.get(p, {}).get(w, {}).get("sb_attr", 0) for p in parent_children)
            if sb_attr_total > 0 and sb_pool.get(w, 0) > 0:
                sbsp = round(sb_pool[w] * sb_attr_this / sb_attr_total, 2)
            else:
                sbsp = sb_data.get(parent, {}).get(w, {}).get("sbsp", 0)
            spend   = round(spsd + sbsp, 2)
            tacos   = round(spend / sales * 100, 1) if sales > 0 else None
            weeks_obj[w] = {
                "sales": round(sales,2), "spsd": round(spsd,2), "sbsp": round(sbsp,2),
                "spend": spend, "units": units, "organic": organic,
                "ppc": ppc, "profits": round(profits,2), "tacos": tacos,
            }

        # ── Apply VINE deduction proportionally by parent's share of total sales ─
        # Pre-compute total account sales per week (sum across ALL parents/children in weekly)
        for w in new_weeks:
            vine_total_w = VINE_DEDUCTIONS.get(w, 0)
            if vine_total_w <= 0:
                continue
            # Total raw sales across ALL known children this week
            total_sales_w = sum(
                sum(weekly.get(a,{}).get(w,{}).get("sales",0) for a in cs)
                for cs in parent_children.values()
            )
            if total_sales_w <= 0:
                continue
            # This parent's raw sales this week (before deduction)
            parent_sales_w = sum(weekly.get(a,{}).get(w,{}).get("sales",0) for a in children)
            share = parent_sales_w / total_sales_w
            vine_deduct = round(vine_total_w * share, 2)
            old_sales = weeks_obj[w]["sales"]
            new_sales = round(max(0, old_sales - vine_deduct), 2)
            weeks_obj[w]["sales"] = new_sales
            spend_w = weeks_obj[w]["spend"]
            weeks_obj[w]["tacos"] = round(spend_w / new_sales * 100, 1) if new_sales > 0 else None

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
    T = TACOS_TARGET
    T18 = int(T * 1.2)
    for old_t, old_t18 in [(70, 84), (20, 24)]:
        html = html.replace(f"'⚠ Above {old_t}%'",  f"'⚠ Above {T}%'")
        html = html.replace(f'"⚠ Above {old_t}%"',  f'"⚠ Above {T}%"')
        html = html.replace(f'<div class="kpi-value kpi-green">{old_t}%</div>', f'<div class="kpi-value kpi-green">{T}%</div>')
        html = html.replace(f"acct<={old_t}?",   f"acct<={T}?")
        html = html.replace(f"acct<={old_t18}?", f"acct<={T18}?")
        html = html.replace(f"TACOS ≤{old_t}%", f"TACOS ≤{T}%")
        html = html.replace(f"> {old_t}", f"> {T}")
        html = html.replace(f">= {old_t}", f">= {T}")

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

    # ── Inject VINE deduction note in nav subtitle ───────────────────────────
    total_vine = sum(VINE_DEDUCTIONS.values())
    html = html.replace(
        f"· SP+SD+SB · TACOS ≤{TACOS_TARGET}%</div>",
        f"· SP+SD+SB · TACOS ≤{TACOS_TARGET}% · VINE -${total_vine:,.0f} deducted</div>"
    )

    # ── Inject Inventory Age tab button ──────────────────────────────────────
    inv_btn = '\n  <button class="tab-btn" onclick="showTab(\'inventory\',this)">📦 Inventory Age</button>'
    if '📦 Inventory Age' not in html:
        _injected = False
        for _lbl in ['🎯 行動清單', '🎯 行動方案', '行動']:
            _a = f'onclick="showPanel(\'action\',this)">{_lbl}</button>'
            if _a in html:
                html = html.replace(_a, _a + inv_btn)
                _injected = True
                break
        if not _injected:
            _last = html.rfind('class="tab-btn"')
            if _last > 0:
                _end = html.find('</button>', _last) + len('</button>')
                html = html[:_end] + inv_btn + html[_end:]

    # ── Build Inventory Age tab HTML ─────────────────────────────────────────
    inv_rows = ""
    for item in sorted(INVENTORY_DATA, key=lambda x: -x["days_of_supply"]):
        dos = item["days_of_supply"]
        if dos > 120:
            dos_class = "color:#dc2626;font-weight:600"
            dos_icon = "🔴"
        elif dos > 60:
            dos_class = "color:#d97706;font-weight:600"
            dos_icon = "🟡"
        else:
            dos_class = "color:#16a34a;font-weight:600"
            dos_icon = "🟢"

        total_age_units = item["age_0_30"] + item["age_31_60"] + item["age_61_90"] + item["age_91_180"] + item["age_181_plus"]
        def pct(n, t=total_age_units): return f"{n/t*100:.0f}%" if t > 0 else "0%"

        age_bar = (
            f'<div style="display:flex;height:8px;border-radius:4px;overflow:hidden;width:120px;background:#f1f5f9">'
            f'<div style="width:{pct(item["age_0_30"])};background:#16a34a" title="0-30d: {item["age_0_30"]}"></div>'
            f'<div style="width:{pct(item["age_31_60"])};background:#84cc16" title="31-60d: {item["age_31_60"]}"></div>'
            f'<div style="width:{pct(item["age_61_90"])};background:#eab308" title="61-90d: {item["age_61_90"]}"></div>'
            f'<div style="width:{pct(item["age_91_180"])};background:#f97316" title="91-180d: {item["age_91_180"]}"></div>'
            f'<div style="width:{pct(item["age_181_plus"])};background:#dc2626" title="181+d: {item["age_181_plus"]}"></div>'
            f'</div>'
        )

        out_of_stock = "⚠️ OOS" if item["available"] == 0 else ""
        inbound_str = f'+{item["inbound_qty"]} inbound' if item["inbound_qty"] > 0 else "—"

        inv_rows += (
            f'<tr style="border-bottom:1px solid var(--border)">'
            f'<td style="padding:8px 12px;font-size:12px;max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">'
            f'  <a href="https://www.amazon.com/dp/{item["asin"]}" target="_blank" style="color:var(--accent);text-decoration:none;font-weight:500">{item["asin"]}</a>'
            f'  <div style="color:var(--text2);font-size:11px;margin-top:2px">{item["name"]}</div>'
            f'</td>'
            f'<td style="padding:8px 12px;text-align:right;font-weight:500">{item["available"]} <span style="color:#dc2626;font-size:11px">{out_of_stock}</span></td>'
            f'<td style="padding:8px 12px">{age_bar}<div style="font-size:10px;color:var(--text2);margin-top:3px">'
            f'{item["age_0_30"]} / {item["age_31_60"]} / {item["age_61_90"]} / {item["age_91_180"]} / {item["age_181_plus"]}</div></td>'
            f'<td style="padding:8px 12px;text-align:right">{item["units_shipped_30"]}</td>'
            f'<td style="padding:8px 12px;text-align:right;{dos_class}">{dos_icon} {int(dos)}d</td>'
            f'<td style="padding:8px 12px;text-align:right;color:var(--text2);font-size:12px">{inbound_str}</td>'
            f'</tr>\n'
        )

    inv_html = (
    '<div id="inventory" class="panel">'
    '<div style="padding:8px 0 20px">'
    '<h2 style="font-size:18px;font-weight:700;margin:0 0 4px">📦 Inventory Age</h2>'
    f'<div style="color:var(--text2);font-size:13px">FBA snapshot · {len(INVENTORY_DATA)} SKUs · sorted by Days of Supply ↓</div>'
    '</div>'
    '<div style="overflow-x:auto">'
    '<table style="width:100%;border-collapse:collapse;font-size:13px">'
    '<thead><tr style="border-bottom:2px solid var(--border)">'
    '<th style="text-align:left;padding:8px 16px 8px 0;color:var(--text2);font-weight:600">Product</th>'
    '<th style="text-align:right;padding:8px 12px;color:var(--text2);font-weight:600">Avail</th>'
    '<th style="text-align:right;padding:8px 12px;color:#16a34a;font-weight:600">0–30d</th>'
    '<th style="text-align:right;padding:8px 12px;color:#84cc16;font-weight:600">31–60d</th>'
    '<th style="text-align:right;padding:8px 12px;color:#eab308;font-weight:600">61–90d</th>'
    '<th style="text-align:right;padding:8px 12px;color:#f97316;font-weight:600">91–180d</th>'
    '<th style="text-align:right;padding:8px 12px;color:#ef4444;font-weight:600">181d+</th>'
    '<th style="text-align:right;padding:8px 12px;color:var(--text2);font-weight:600">Sold/30d</th>'
    '<th style="text-align:right;padding:8px 12px;color:var(--text2);font-weight:600">DoS</th>'
    '<th style="text-align:right;padding:8px 12px;color:var(--text2);font-weight:600">Inbound</th>'
    '</tr></thead><tbody>'
) + ''.join(
    '<tr style="border-bottom:1px solid var(--border);' + (
        'background:rgba(239,68,68,0.06)' if row['days_of_supply'] > 120
        else 'background:rgba(234,179,8,0.06)' if row['days_of_supply'] > 60
        else ''
    ) + '">'
    '<td style="padding:9px 16px 9px 0">'
    '<div style="font-weight:600">' + row['name'] + '</div>'
    '<div style="color:var(--text2);font-size:11px">' + row['asin'] + '</div>'
    '</td>'
    '<td style="text-align:right;padding:9px 12px">' + str(row['available']) + '</td>'
    '<td style="text-align:right;padding:9px 12px;color:#16a34a">' + (str(row['age_0_30']) if row['age_0_30'] else '—') + '</td>'
    '<td style="text-align:right;padding:9px 12px;color:#84cc16">' + (str(row['age_31_60']) if row['age_31_60'] else '—') + '</td>'
    '<td style="text-align:right;padding:9px 12px;color:#eab308">' + (str(row['age_61_90']) if row['age_61_90'] else '—') + '</td>'
    '<td style="text-align:right;padding:9px 12px;color:#f97316">' + (str(row['age_91_180']) if row['age_91_180'] else '—') + '</td>'
    '<td style="text-align:right;padding:9px 12px;color:#ef4444">' + (str(row['age_181_plus']) if row['age_181_plus'] else '—') + '</td>'
    '<td style="text-align:right;padding:9px 12px">' + str(row['units_shipped_30']) + '</td>'
    '<td style="text-align:right;padding:9px 12px;font-weight:700;color:' + (
        '#ef4444' if row['days_of_supply'] > 120
        else '#eab308' if row['days_of_supply'] > 60
        else '#16a34a'
    ) + '">' + (str(row['days_of_supply']) if row['days_of_supply'] < 9999 else '∞') + '</td>'
    '<td style="text-align:right;padding:9px 12px;color:var(--text2)">' + (str(row['inbound_qty']) if row['inbound_qty'] else '—') + '</td>'
    '</tr>'
    for row in sorted(INVENTORY_DATA, key=lambda x: -x['days_of_supply'])
) + '</tbody></table></div></div>'


    # Insert inventory panel before </body>
    html = html.replace("</body>", inv_html + "\n</body>", 1)

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
        "<title>{CLIENT_NAME} · {MARKET} Market — Feb–Mar 2026</title>",
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
    html = html.replace('"DBJ US · Feb–Mar 2026"',
                        f'"{CLIENT_NAME} {MARKET} · {REPORT_PERIOD}"')

    # ── Inject download button inline with "Sales & Ad Spend" title ──────
    xlsx_name = f"{CLIENT_NAME}_US_{REPORT_PERIOD.replace('–', '-').replace(' ', '_')}.xlsx"
    old_title = (
        f'<div style="font-size:28px;font-weight:800;color:var(--accent);'
        f'font-family:var(--display);margin-bottom:4px">'
        f'Sales &amp; Ad Spend — {REPORT_PERIOD}</div>'
    )
    new_title = (
        f'<div style="display:flex;align-items:center;gap:16px;margin-bottom:4px">'
        f'<div style="font-size:28px;font-weight:800;color:var(--accent);'
        f'font-family:var(--display)">Sales &amp; Ad Spend — {REPORT_PERIOD}</div>'
        f'<a href="./{xlsx_name}" download="{xlsx_name}" target="_blank" '
        f'style="display:inline-flex;align-items:center;gap:6px;padding:7px 16px;'
        f'background:#16a34a;color:#fff;border-radius:6px;font-size:13px;font-weight:600;'
        f'text-decoration:none;white-space:nowrap;font-family:Inter,sans-serif">'
        f'⬇ Download Excel</a></div>'
    )
    html = html.replace(old_title, new_title)

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
    weekly, sb_pool = load_sales(SALES_CSV)
    sb_data = load_sb(SB_CSV, child_to_parent)

    # 2. DBJ: no frozen weeks — all data from CSV
    frozen_parents, frozen_children = {}, {}
    print(f"  All weeks computed from CSV")

    # 3. Build data model
    parents, child_data = build_data(weekly, child_to_parent, asin_to_name, sb_data,
                                     sb_pool, frozen_parents, frozen_children)

    print(f"\n  {'Product':<14}  {'Sales':>10}  {'Spend':>8}  {'TACOS':>7}  Children")
    print("  " + "─" * 54)
    total_all = 0
    for pid, p in sorted(parents.items(), key=lambda x: -x[1]["total_sales"]):
        zh = PARENT_SHORTS.get(pid, pid)
        tc = f"{p['tacos_4w']}%" if p['tacos_4w'] else "—"
        print(f"  {zh:<14}  {CURRENCY}{p['total_sales']:>9,.0f}  {CURRENCY}{p['total_spend']:>7,.0f}  {tc:>7}  {len(p['children'])} child ASINs")
        total_all += p['total_sales']
    vine_total = sum(VINE_DEDUCTIONS.values())
    print(f"\n  Total Sales (VINE-adjusted): {CURRENCY}{total_all:,.0f}")
    print(f"  VINE deducted: {CURRENCY}{vine_total:,.0f}  (W1=${VINE_DEDUCTIONS['W1']:,.0f} W2=${VINE_DEDUCTIONS['W2']:,.0f} W3=${VINE_DEDUCTIONS['W3']:,.0f} W4=${VINE_DEDUCTIONS['W4']:,.0f})")

    # 3. Load base HTML template (DAIKEN light-theme HTML as base)
    BASE_TEMPLATE = Path("/Users/koda/amazon-autopilot/output/daiken/DAIKEN_US_Feb-Mar_2026.html")
    with open(BASE_TEMPLATE, encoding="utf-8") as f:
        html = f.read()

    html = apply_light_theme(html)
    html = inject_data(html, parents, child_data)
    html = inject_week_buttons(html)
    html = inject_title_labels(html)

    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\n  ✓ Output → {OUTPUT_HTML.name}  ({len(html):,} chars)")
    print("─" * 56)
