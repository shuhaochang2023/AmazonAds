#!/usr/bin/env python3
"""
HALO Bulk — Generate SP Product Targeting campaigns from HALO cross-sell data.

Usage:
  python3 api/halo_bulk.py geo           # generate bulk xlsx for GEO
  python3 api/halo_bulk.py daiken        # generate for DAIKEN
  python3 api/halo_bulk.py flux-de       # generate for Flux DE
  python3 api/halo_bulk.py --max 10 geo  # limit to top 10 pairs

Output: clients/{brand}/bulk-output/HALO_{BRAND}_{timestamp}.xlsx
"""

import sys
import csv
import json
from pathlib import Path
from datetime import datetime

try:
    import openpyxl
except ImportError:
    print("ERROR: openpyxl required. pip install openpyxl")
    sys.exit(1)

ROOT = Path(__file__).resolve().parent.parent

# Brand configs — bid, budget, naming
BRAND_CONFIG = {
    "daiken": {"bid": 2.00, "budget": 5.00, "label": "DAIKEN", "prefix": "DK"},
    "dbj":    {"bid": 0.55, "budget": 5.00, "label": "DBJ",    "prefix": "DBJ"},
    "geo":    {"bid": 0.16, "budget": 5.00, "label": "GEO",    "prefix": "GEO"},
    "braintea": {"bid": 0.50, "budget": 5.00, "label": "BrainTea", "prefix": "BT"},
    "flux-au": {"bid": 0.55, "budget": 5.00, "label": "Flux AU", "prefix": "FX-AU"},
    "flux-uk": {"bid": 0.55, "budget": 5.00, "label": "Flux UK", "prefix": "FX-UK"},
    "flux-de": {"bid": 0.55, "budget": 5.00, "label": "Flux DE", "prefix": "FX-DE"},
    "flux-us": {"bid": 0.55, "budget": 5.00, "label": "Flux US", "prefix": "FX-US"},
    "flux-ca": {"bid": 0.55, "budget": 5.00, "label": "Flux CA", "prefix": "FX-CA"},
}

# Columns matching Amazon bulk format
HEADERS = [
    "Record ID", "Record Type", "Campaign ID", "Campaign Name",
    "Campaign Daily Budget", "Portfolio ID", "Campaign Start Date",
    "Campaign End Date", "Campaign Targeting Type", "Campaign Status",
    "Campaign Bidding Strategy", "Ad Group ID", "Ad Group Name",
    "Ad Group Default Bid", "Ad Group Status", "SKU", "ASIN", "Ad ID",
    "Ad Group Ad Status", "Keyword ID", "Keyword", "Match Type",
    "Keyword Status", "Keyword Bid", "Product Targeting ID",
    "Product Targeting Expression", "Product Targeting Bid",
    "Product Targeting Status",
]


def halo_dir(brand_key):
    if brand_key.startswith("flux-"):
        market = brand_key.split("-")[1]
        return ROOT / f"clients/flux/halo/{market}"
    return ROOT / f"clients/{brand_key}/halo"


def products_csv(brand_key):
    if brand_key.startswith("flux-"):
        market = brand_key.split("-")[1]
        return ROOT / f"clients/flux/input/{market}/Products.csv"
    return ROOT / f"clients/{brand_key}/input/Products.csv"


def bulk_output_dir(brand_key):
    if brand_key.startswith("flux-"):
        market = brand_key.split("-")[1]
        d = ROOT / f"clients/flux/bulk-output"
    else:
        d = ROOT / f"clients/{brand_key}/bulk-output"
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_sku_map(brand_key):
    csv_path = products_csv(brand_key)
    sku_map = {}
    if not csv_path.exists():
        print(f"  Products.csv not found: {csv_path}")
        return sku_map
    with open(csv_path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            asin = (row.get("ASIN") or "").strip()
            sku = (row.get("SKU") or "").strip()
            name = (row.get("Short Name") or row.get("Title") or "").strip()[:30]
            if asin and sku:
                sku_map[asin] = {"sku": sku, "name": name}
    return sku_map


def build_pairs(brand_key, max_pairs=15):
    """Extract top cross-sell pairs from halo analysis."""
    analysis_path = halo_dir(brand_key) / "halo_analysis.json"
    if not analysis_path.exists():
        print(f"  No halo_analysis.json — run: python3 api/halo.py analyze {brand_key}")
        return []

    with open(analysis_path) as f:
        a = json.load(f)

    sku_map = load_sku_map(brand_key)
    if not sku_map:
        return []

    pairs = []
    seen = set()
    for adv, pa in sorted(a.get("per_asin", {}).items(),
                           key=lambda x: x[1]["halo_total"], reverse=True):
        adv_info = sku_map.get(adv)
        if not adv_info or not adv_info["sku"]:
            continue
        for h in pa.get("top_halo", [])[:2]:
            target = h["asin"]
            if target == adv:
                continue
            pair_key = f"{adv}_{target}"
            if pair_key in seen:
                continue
            seen.add(pair_key)
            pairs.append({
                "adv_asin": adv,
                "adv_sku": adv_info["sku"],
                "adv_name": adv_info["name"],
                "target_asin": target,
                "target_name": sku_map.get(target, {}).get("name", target[:15]),
                "purchases": h["purchases"],
                "sales": h["sales"],
            })
            if len(pairs) >= max_pairs:
                return pairs
    return pairs


def generate_bulk(brand_key, max_pairs=15):
    cfg = BRAND_CONFIG[brand_key]
    bid = cfg["bid"]
    budget = cfg["budget"]
    prefix = cfg["prefix"]
    label = cfg["label"]
    ts = datetime.now().strftime("%Y%m%d_%H%M")

    pairs = build_pairs(brand_key, max_pairs)
    if not pairs:
        print(f"  No valid cross-sell pairs for {label}")
        return None

    print(f"\n  {label} — {len(pairs)} HALO cross-sell campaigns")
    print(f"  Bid: ${bid}  Budget: ${budget}")
    print(f"  {'─'*55}")

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sponsored Products Campaigns"
    ws.append(HEADERS)

    for p in pairs:
        adv_short = p["adv_name"][:15] or p["adv_asin"][-5:]
        tgt_short = p["target_name"][:15] or p["target_asin"][-5:]
        camp_name = f"SP_HALO_{prefix}_{p['adv_asin']}_vs_{p['target_asin']}_{ts}"
        ag_name = f"AG_HALO_{p['adv_asin']}_{p['target_asin']}"

        # Row 1: Campaign
        row_camp = [None] * len(HEADERS)
        row_camp[1] = "Campaign"
        row_camp[2] = camp_name  # Campaign ID = Campaign Name
        row_camp[3] = camp_name
        row_camp[4] = budget
        row_camp[8] = "Manual"
        row_camp[9] = "enabled"
        row_camp[10] = "Dynamic bids - down only"
        ws.append(row_camp)

        # Row 2: Ad Group
        row_ag = [None] * len(HEADERS)
        row_ag[1] = "Ad Group"
        row_ag[2] = camp_name
        row_ag[3] = camp_name
        row_ag[11] = ag_name
        row_ag[12] = ag_name
        row_ag[13] = bid
        row_ag[14] = "enabled"
        ws.append(row_ag)

        # Row 3: Product Ad (advertised ASIN)
        row_pa = [None] * len(HEADERS)
        row_pa[1] = "Product Ad"
        row_pa[2] = camp_name
        row_pa[3] = camp_name
        row_pa[11] = ag_name
        row_pa[12] = ag_name
        row_pa[15] = p["adv_sku"]
        row_pa[16] = p["adv_asin"]
        row_pa[18] = "enabled"
        ws.append(row_pa)

        # Row 4: Product Targeting (target ASIN)
        row_pt = [None] * len(HEADERS)
        row_pt[1] = "Product Targeting"
        row_pt[2] = camp_name
        row_pt[3] = camp_name
        row_pt[11] = ag_name
        row_pt[12] = ag_name
        row_pt[25] = f'asin="{p["target_asin"]}"'
        row_pt[26] = bid
        row_pt[27] = "enabled"
        ws.append(row_pt)

        print(f"    {p['adv_asin']} ({adv_short}) → {p['target_asin']} ({tgt_short})  {p['purchases']}p ${p['sales']:,.2f}")

    # Save
    out_dir = bulk_output_dir(brand_key)
    filename = f"HALO_{prefix}_{ts}.xlsx"
    out_path = out_dir / filename
    wb.save(out_path)
    print(f"\n  Saved: {out_path}")
    print(f"  Campaigns: {len(pairs)}  |  Rows: {len(pairs) * 4 + 1}")
    return out_path


def main():
    raw_args = sys.argv[1:]
    max_pairs = 15

    args = []
    skip_next = False
    for i, a in enumerate(raw_args):
        if skip_next:
            skip_next = False
            continue
        if a == "--max" and i + 1 < len(raw_args):
            max_pairs = int(raw_args[i + 1])
            skip_next = True
        elif not a.startswith("--"):
            args.append(a)

    if not args:
        print(__doc__)
        return

    flux_markets = ["flux-au", "flux-uk", "flux-de", "flux-us", "flux-ca"]

    targets = []
    for a in args:
        if a == "flux":
            targets.extend(flux_markets)
        elif a in BRAND_CONFIG:
            targets.append(a)
        else:
            print(f"  Unknown brand: {a}")

    for brand_key in targets:
        generate_bulk(brand_key, max_pairs)


if __name__ == "__main__":
    main()
