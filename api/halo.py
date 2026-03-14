#!/usr/bin/env python3
"""
HALO — Cross-Sell / Conquest / Defense Intelligence
3-step pipeline: pull → analyze → report. Run one brand at a time.

Usage (step-by-step):
  python3 api/halo.py pull daiken              # Step 1: pull raw data
  python3 api/halo.py analyze daiken           # Step 2: classify halo vs leakage
  python3 api/halo.py report daiken            # Step 3: generate HTML panel

Options:
  python3 api/halo.py pull daiken --days 60    # custom lookback (default 90)
  python3 api/halo.py pull flux                # all 5 flux markets
  python3 api/halo.py run daiken               # run all 3 steps at once

Available brands: daiken, dbj, geo, braintea, flux-au, flux-uk, flux-de, flux-us, flux-ca, flux (all 5)
"""

import os
import sys
import json
import time
import csv
from pathlib import Path
from datetime import date, timedelta
from collections import defaultdict
from html import escape

ROOT = Path(__file__).resolve().parent.parent

# ── Load credentials ─────────────────────────────────────
env_path = ROOT / ".env"
with open(env_path) as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, val = line.split("=", 1)
            if key == "AMAZON_ADS_CLIENT_ID":
                os.environ["AD_API_CLIENT_ID"] = val
            elif key == "AMAZON_ADS_CLIENT_SECRET":
                os.environ["AD_API_CLIENT_SECRET"] = val
            elif key == "AMAZON_ADS_REFRESH_TOKEN":
                os.environ["AD_API_REFRESH_TOKEN"] = val

os.environ["AD_API_PROFILE_ID"] = "0"

from ad_api.api import Reports as ReportsV3
from ad_api.base.marketplaces import Marketplaces

# ── Brand configs ────────────────────────────────────────
BRANDS = {
    "daiken": {
        "profile_id": "1243647931853395",
        "marketplace": Marketplaces.US,
        "label": "DAIKEN",
        "products_csv": ROOT / "clients/daiken/input/Products.csv",
    },
    "dbj": {
        "profile_id": "3565954576012304",
        "marketplace": Marketplaces.US,
        "label": "DBJ",
        "products_csv": ROOT / "clients/dbj/input/Products.csv",
    },
    "geo": {
        "profile_id": "3947387233604911",
        "marketplace": Marketplaces.US,
        "label": "GEO",
        "products_csv": ROOT / "clients/geo/input/Products.csv",
    },
    "braintea": {
        "profile_id": "2695717242300933",
        "marketplace": Marketplaces.US,
        "label": "Brain Tea",
        "products_csv": ROOT / "clients/braintea/input/Products.csv",
    },
    "flux-au": {
        "profile_id": "3601686309797276",
        "marketplace": Marketplaces.AU,
        "label": "Flux AU",
        "products_csv": ROOT / "clients/flux/input/au/Products.csv",
    },
    "flux-uk": {
        "profile_id": "2347387401732870",
        "marketplace": Marketplaces.UK,
        "label": "Flux UK",
        "products_csv": ROOT / "clients/flux/input/uk/Products.csv",
    },
    "flux-de": {
        "profile_id": "4003401656487187",
        "marketplace": Marketplaces.EU,
        "label": "Flux DE",
        "products_csv": ROOT / "clients/flux/input/de/Products.csv",
    },
    "flux-us": {
        "profile_id": "3255856020251415",
        "marketplace": Marketplaces.US,
        "label": "Flux US",
        "products_csv": ROOT / "clients/flux/input/us/Products.csv",
    },
    "flux-ca": {
        "profile_id": "599373744640869",
        "marketplace": Marketplaces.CA,
        "label": "Flux CA",
        "products_csv": ROOT / "clients/flux/input/ca/Products.csv",
    },
}

FLUX_MARKETS = ["flux-au", "flux-uk", "flux-de", "flux-us", "flux-ca"]


def halo_dir(brand_key):
    """Output directory for HALO data per brand."""
    if brand_key.startswith("flux-"):
        market = brand_key.split("-")[1]
        return ROOT / f"clients/flux/halo/{market}"
    return ROOT / f"clients/{brand_key}/halo"


# ── Auto-load own ASINs from Products.csv ────────────────
def load_own_asins(brand_key):
    cfg = BRANDS[brand_key]
    csv_path = cfg["products_csv"]
    asins = set()
    if not csv_path.exists():
        print(f"  ⚠ Products.csv not found: {csv_path}")
        return asins
    with open(csv_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            asin = row.get("ASIN") or row.get("asin") or row.get("Advertised ASIN") or ""
            asin = asin.strip()
            if asin and asin.startswith("B0"):
                asins.add(asin)
    print(f"  Own ASINs loaded: {len(asins)} from Products.csv")
    return asins


# ── API: Pull spPurchasedProduct ─────────────────────────
def _request_and_wait(api, label, chunk_start, chunk_end):
    """Request one spPurchasedProduct report chunk and wait for completion."""
    body = {
        "name": f"{label} HALO {chunk_start}→{chunk_end}",
        "startDate": chunk_start.isoformat(),
        "endDate": chunk_end.isoformat(),
        "configuration": {
            "adProduct": "SPONSORED_PRODUCTS",
            "reportTypeId": "spPurchasedProduct",
            "format": "GZIP_JSON",
            "groupBy": ["asin"],
            "columns": [
                "campaignName", "campaignId",
                "adGroupName", "adGroupId",
                "advertisedAsin", "purchasedAsin",
                "purchasesOtherSku7d", "salesOtherSku7d", "unitsSoldOtherSku7d",
            ],
            "timeUnit": "SUMMARY",
        },
    }

    try:
        resp = api.post_report(body=body)
        report_id = resp.payload.get("reportId")
        print(f"    Chunk {chunk_start}→{chunk_end}: requested {report_id}")
    except Exception as e:
        print(f"    Chunk {chunk_start}→{chunk_end}: ERROR {e}")
        return []

    elapsed = 0
    max_wait = 600
    while elapsed < max_wait:
        resp = api.get_report(report_id)
        status = resp.payload.get("status")
        if status == "COMPLETED":
            url = resp.payload.get("url")
            dl = api.download_report(url=url, format="data")
            data = dl.payload or []
            print(f"    Chunk {chunk_start}→{chunk_end}: {len(data)} rows")
            return data
        elif status == "FAILED":
            print(f"    Chunk FAILED: {resp.payload}")
            return []
        time.sleep(10)
        elapsed += 10

    print(f"    Chunk timeout ({max_wait}s)")
    return []


def pull_report(brand_key, start_date, end_date):
    """Pull spPurchasedProduct in 30-day chunks (API max = 31 days), then merge."""
    cfg = BRANDS[brand_key]
    profile_id = cfg["profile_id"]
    marketplace = cfg["marketplace"]
    out = halo_dir(brand_key)
    out.mkdir(parents=True, exist_ok=True)

    os.environ["AD_API_PROFILE_ID"] = profile_id
    api = ReportsV3(marketplace=marketplace)

    print(f"\n{'─'*55}")
    print(f"  {cfg['label']} | Profile {profile_id}")
    print(f"  Period: {start_date} → {end_date}")
    print(f"{'─'*55}")

    # Split into 30-day chunks
    chunks = []
    cs = start_date
    while cs <= end_date:
        ce = min(cs + timedelta(days=29), end_date)
        chunks.append((cs, ce))
        cs = ce + timedelta(days=1)

    print(f"  Pulling {len(chunks)} chunk(s)...")

    all_data = []
    for cs, ce in chunks:
        chunk_data = _request_and_wait(api, cfg["label"], cs, ce)
        all_data.extend(chunk_data)

    if not all_data:
        print(f"  No data returned")
        return None

    # Save merged result
    json_path = out / f"halo_raw_{end_date}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(all_data, f, ensure_ascii=False, indent=2)

    csv_path = json_path.with_suffix(".csv")
    keys = all_data[0].keys()
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(all_data)

    print(f"  Merged: {len(all_data)} total rows → {json_path.name}")
    return all_data


# ── Analysis ─────────────────────────────────────────────
def analyze(brand_key, data=None):
    out = halo_dir(brand_key)
    own_asins = load_own_asins(brand_key)
    label = BRANDS[brand_key]["label"]

    if not own_asins:
        print(f"  Skipping analysis — no own ASINs")
        return None

    # Load from file if not provided
    if data is None:
        files = sorted(out.glob("halo_raw_*.json"), reverse=True)
        if not files:
            print(f"  No HALO data found for {brand_key}")
            return None
        with open(files[0], encoding="utf-8") as f:
            data = json.load(f)
        print(f"  Loaded: {files[0].name} ({len(data)} rows)")

    if not data:
        print(f"  Empty dataset")
        return None

    # ── Aggregate by advertisedAsin → purchasedAsin ──
    # Every row = cross-purchase (ad for A → customer bought B)
    # Halo = B is own brand (cross-sell win)
    # Leakage = B is competitor (lost to competition)
    # Columns: purchasesOtherSku7d, salesOtherSku7d, unitsSoldOtherSku7d

    halo_sales = defaultdict(lambda: {"purchases": 0, "sales": 0.0, "units": 0})
    leakage = defaultdict(lambda: {"purchases": 0, "sales": 0.0, "units": 0})

    # Per advertised ASIN breakdown
    per_asin = defaultdict(lambda: {
        "halo": defaultdict(lambda: {"purchases": 0, "sales": 0.0, "units": 0}),
        "leakage": defaultdict(lambda: {"purchases": 0, "sales": 0.0, "units": 0}),
    })

    for row in data:
        adv = row.get("advertisedAsin", "")
        pur = row.get("purchasedAsin", "")
        if not adv or not pur:
            continue

        purchases = int(row.get("purchasesOtherSku7d", 0) or 0)
        sales = float(row.get("salesOtherSku7d", 0) or 0)
        units = int(row.get("unitsSoldOtherSku7d", 0) or 0)

        if purchases == 0 and sales == 0:
            continue

        if pur in own_asins:
            # Halo — bought different own product
            halo_sales[pur]["purchases"] += purchases
            halo_sales[pur]["sales"] += sales
            halo_sales[pur]["units"] += units
            per_asin[adv]["halo"][pur]["purchases"] += purchases
            per_asin[adv]["halo"][pur]["sales"] += sales
            per_asin[adv]["halo"][pur]["units"] += units
        else:
            # Leakage — bought competitor product
            leakage[pur]["purchases"] += purchases
            leakage[pur]["sales"] += sales
            leakage[pur]["units"] += units
            per_asin[adv]["leakage"][pur]["purchases"] += purchases
            per_asin[adv]["leakage"][pur]["sales"] += sales
            per_asin[adv]["leakage"][pur]["units"] += units

    # ── Sort ──
    top_halo = sorted(halo_sales.items(), key=lambda x: x[1]["sales"], reverse=True)
    top_leakage = sorted(leakage.items(), key=lambda x: x[1]["purchases"], reverse=True)

    # ── Totals ──
    total_halo_sales = sum(d["sales"] for d in halo_sales.values())
    total_halo_purchases = sum(d["purchases"] for d in halo_sales.values())
    total_leak_sales = sum(d["sales"] for d in leakage.values())
    total_leak_purchases = sum(d["purchases"] for d in leakage.values())
    total_all_sales = total_halo_sales + total_leak_sales
    total_all_purchases = total_halo_purchases + total_leak_purchases

    halo_pct = (total_halo_sales / total_all_sales * 100) if total_all_sales else 0
    leak_pct = (total_leak_sales / total_all_sales * 100) if total_all_sales else 0

    # ── Print summary ──
    print(f"\n  {'='*50}")
    print(f"  {label} — HALO Analysis")
    print(f"  {'='*50}")
    print(f"  Halo (own):     {total_halo_purchases:,} purchases  ${total_halo_sales:,.2f} ({halo_pct:.1f}%)")
    print(f"  Leakage (comp): {total_leak_purchases:,} purchases  ${total_leak_sales:,.2f} ({leak_pct:.1f}%)")
    print(f"  {'─'*50}")

    if top_halo:
        print(f"  Top Halo Products (own-brand cross-sell):")
        for asin, d in top_halo[:5]:
            print(f"    {asin}: {d['purchases']} purchases, ${d['sales']:,.2f}")

    if top_leakage:
        print(f"  Top Leakage (conquest targets / defense):")
        for asin, d in top_leakage[:10]:
            print(f"    {asin}: {d['purchases']} purchases, ${d['sales']:,.2f}")

    # ── Save analysis JSON ──
    out.mkdir(parents=True, exist_ok=True)
    analysis = {
        "brand": brand_key,
        "label": label,
        "date": date.today().isoformat(),
        "own_asin_count": len(own_asins),
        "total_rows": len(data),
        "summary": {
            "halo": {"purchases": total_halo_purchases, "sales": round(total_halo_sales, 2), "pct": round(halo_pct, 1)},
            "leakage": {"purchases": total_leak_purchases, "sales": round(total_leak_sales, 2), "pct": round(leak_pct, 1)},
        },
        "top_halo": [{"asin": a, **d} for a, d in top_halo[:20]],
        "top_leakage": [{"asin": a, **d} for a, d in top_leakage[:30]],
        "per_asin": {
            adv: {
                "halo_total": sum(h["sales"] for h in pa["halo"].values()),
                "leak_total": sum(l["sales"] for l in pa["leakage"].values()),
                "top_halo": sorted(
                    [{"asin": a, **d} for a, d in pa["halo"].items()],
                    key=lambda x: x["sales"], reverse=True
                )[:5],
                "top_leakage": sorted(
                    [{"asin": a, **d} for a, d in pa["leakage"].items()],
                    key=lambda x: x["purchases"], reverse=True
                )[:10],
            }
            for adv, pa in per_asin.items()
            if sum(h["sales"] for h in pa["halo"].values()) + sum(l["sales"] for l in pa["leakage"].values()) > 0
        },
    }

    analysis_path = out / "halo_analysis.json"
    with open(analysis_path, "w", encoding="utf-8") as f:
        json.dump(analysis, f, ensure_ascii=False, indent=2)
    print(f"  Saved: {analysis_path}")

    # ── Generate HTML snippet ──
    html_path = out / "halo_panel.html"
    html = generate_html(analysis)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  HTML:  {html_path}")

    return analysis


# ── HTML Panel Generator ─────────────────────────────────
def generate_html(a):
    """Generate a standalone HALO dashboard panel for embedding."""
    s = a["summary"]
    label = escape(a["label"])
    d = a["date"]

    def fmt_money(v):
        return f"${v:,.2f}"

    def pct_bar(pct, color):
        return f'<div style="background:rgba(0,0,0,.06);border-radius:3px;height:6px;width:100%;margin-top:4px;"><div style="background:{color};border-radius:3px;height:6px;width:{min(pct, 100):.1f}%;"></div></div>'

    total_cross = s["halo"]["sales"] + s["leakage"]["sales"]

    # KPI strip
    kpi = f'''<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:1px;background:var(--border,#e2e8f0);border-radius:10px;overflow:hidden;margin-bottom:16px;">
  <div style="background:var(--surface,#fff);padding:16px 18px;">
    <div style="font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--text,#0f172a);text-transform:uppercase;letter-spacing:.08em;">Cross-Purchase Total</div>
    <div style="font-family:'JetBrains Mono',monospace;font-size:20px;font-weight:700;color:var(--text,#0f172a);margin-top:4px;">{fmt_money(total_cross)}</div>
    <div style="font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--dim,#64748b);">{s["halo"]["purchases"] + s["leakage"]["purchases"]:,} purchases</div>
  </div>
  <div style="background:var(--surface,#fff);padding:16px 18px;">
    <div style="font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--green,#16a34a);text-transform:uppercase;letter-spacing:.08em;">Halo 光環</div>
    <div style="font-family:'JetBrains Mono',monospace;font-size:20px;font-weight:700;color:var(--green,#16a34a);margin-top:4px;">{fmt_money(s["halo"]["sales"])}</div>
    <div style="font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--dim,#64748b);">{s["halo"]["purchases"]:,} purchases · {s["halo"]["pct"]}%</div>
    {pct_bar(s["halo"]["pct"], "var(--green,#16a34a)")}
  </div>
  <div style="background:var(--surface,#fff);padding:16px 18px;">
    <div style="font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--red,#dc2626);text-transform:uppercase;letter-spacing:.08em;">Leakage 流失</div>
    <div style="font-family:'JetBrains Mono',monospace;font-size:20px;font-weight:700;color:var(--red,#dc2626);margin-top:4px;">{fmt_money(s["leakage"]["sales"])}</div>
    <div style="font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--dim,#64748b);">{s["leakage"]["purchases"]:,} purchases · {s["leakage"]["pct"]}%</div>
    {pct_bar(s["leakage"]["pct"], "var(--red,#dc2626)")}
  </div>
</div>'''

    # Top Halo table
    halo_rows = ""
    for i, h in enumerate(a["top_halo"][:10], 1):
        halo_rows += f'''<tr>
  <td style="text-align:left;font-family:'JetBrains Mono',monospace;font-size:12px;padding:6px 10px;">{i}</td>
  <td style="text-align:left;font-family:'JetBrains Mono',monospace;font-size:12px;padding:6px 10px;font-weight:600;">{escape(h["asin"])}</td>
  <td style="text-align:right;font-family:'JetBrains Mono',monospace;font-size:12px;padding:6px 10px;">{h["purchases"]:,}</td>
  <td style="text-align:right;font-family:'JetBrains Mono',monospace;font-size:12px;padding:6px 10px;">{fmt_money(h["sales"])}</td>
  <td style="text-align:right;font-family:'JetBrains Mono',monospace;font-size:12px;padding:6px 10px;">{h["units"]:,}</td>
</tr>'''

    halo_table = f'''<div style="margin-bottom:16px;">
<div style="font-family:'JetBrains Mono',monospace;font-size:11px;font-weight:700;color:var(--green,#16a34a);text-transform:uppercase;letter-spacing:.08em;padding:0 0 8px;">Top Halo Products 光環銷售 — own-brand cross-sell</div>
<div style="border:1px solid var(--border,#e2e8f0);border-radius:8px;overflow:hidden;">
<table style="width:100%;border-collapse:collapse;">
<thead><tr style="background:var(--bg3,#f8fafc);">
  <th style="text-align:left;font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--dim,#64748b);padding:7px 10px;text-transform:uppercase;letter-spacing:.08em;border-bottom:1px solid var(--border,#e2e8f0);">#</th>
  <th style="text-align:left;font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--dim,#64748b);padding:7px 10px;text-transform:uppercase;letter-spacing:.08em;border-bottom:1px solid var(--border,#e2e8f0);">ASIN</th>
  <th style="text-align:right;font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--dim,#64748b);padding:7px 10px;text-transform:uppercase;letter-spacing:.08em;border-bottom:1px solid var(--border,#e2e8f0);">Purchases</th>
  <th style="text-align:right;font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--dim,#64748b);padding:7px 10px;text-transform:uppercase;letter-spacing:.08em;border-bottom:1px solid var(--border,#e2e8f0);">Sales</th>
  <th style="text-align:right;font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--dim,#64748b);padding:7px 10px;text-transform:uppercase;letter-spacing:.08em;border-bottom:1px solid var(--border,#e2e8f0);">Units</th>
</tr></thead>
<tbody>{halo_rows}</tbody>
</table></div></div>''' if halo_rows else ""

    # Top Leakage table
    leak_rows = ""
    for i, l in enumerate(a["top_leakage"][:15], 1):
        leak_rows += f'''<tr>
  <td style="text-align:left;font-family:'JetBrains Mono',monospace;font-size:12px;padding:6px 10px;">{i}</td>
  <td style="text-align:left;font-family:'JetBrains Mono',monospace;font-size:12px;padding:6px 10px;font-weight:600;">{escape(l["asin"])}</td>
  <td style="text-align:right;font-family:'JetBrains Mono',monospace;font-size:12px;padding:6px 10px;">{l["purchases"]:,}</td>
  <td style="text-align:right;font-family:'JetBrains Mono',monospace;font-size:12px;padding:6px 10px;">{fmt_money(l["sales"])}</td>
  <td style="text-align:right;font-family:'JetBrains Mono',monospace;font-size:12px;padding:6px 10px;">{l["units"]:,}</td>
</tr>'''

    leak_table = f'''<div style="margin-bottom:16px;">
<div style="font-family:'JetBrains Mono',monospace;font-size:11px;font-weight:700;color:var(--red,#dc2626);text-transform:uppercase;letter-spacing:.08em;padding:0 0 8px;">Top Leakage 流失目標 — conquest targets / defense priorities</div>
<div style="border:1px solid var(--border,#e2e8f0);border-radius:8px;overflow:hidden;">
<table style="width:100%;border-collapse:collapse;">
<thead><tr style="background:var(--bg3,#f8fafc);">
  <th style="text-align:left;font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--dim,#64748b);padding:7px 10px;text-transform:uppercase;letter-spacing:.08em;border-bottom:1px solid var(--border,#e2e8f0);">#</th>
  <th style="text-align:left;font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--dim,#64748b);padding:7px 10px;text-transform:uppercase;letter-spacing:.08em;border-bottom:1px solid var(--border,#e2e8f0);">ASIN</th>
  <th style="text-align:right;font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--dim,#64748b);padding:7px 10px;text-transform:uppercase;letter-spacing:.08em;border-bottom:1px solid var(--border,#e2e8f0);">Purchases</th>
  <th style="text-align:right;font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--dim,#64748b);padding:7px 10px;text-transform:uppercase;letter-spacing:.08em;border-bottom:1px solid var(--border,#e2e8f0);">Sales</th>
  <th style="text-align:right;font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--dim,#64748b);padding:7px 10px;text-transform:uppercase;letter-spacing:.08em;border-bottom:1px solid var(--border,#e2e8f0);">Units</th>
</tr></thead>
<tbody>{leak_rows}</tbody>
</table></div></div>''' if leak_rows else ""

    # Per-ASIN breakdown
    asin_sections = ""
    sorted_asins = sorted(
        a["per_asin"].items(),
        key=lambda x: x[1]["halo_total"] + x[1]["leak_total"],
        reverse=True,
    )
    for adv, pa in sorted_asins[:8]:
        total = pa["halo_total"] + pa["leak_total"]
        if total == 0:
            continue
        halo_p = (pa["halo_total"] / total * 100) if total else 0
        leak_p = (pa["leak_total"] / total * 100) if total else 0

        mini_halo = ""
        if pa["top_halo"]:
            items = ", ".join(f'{h["asin"]}({h["purchases"]})' for h in pa["top_halo"][:3])
            mini_halo = f'<div style="font-size:11px;color:var(--green,#16a34a);">Halo: {items}</div>'

        mini_leak = ""
        if pa["top_leakage"]:
            items = ", ".join(f'{l["asin"]}({l["purchases"]})' for l in pa["top_leakage"][:3])
            mini_leak = f'<div style="font-size:11px;color:var(--red,#dc2626);">Leak: {items}</div>'

        asin_sections += f'''<div style="border:1px solid var(--border,#e2e8f0);border-radius:8px;padding:12px 14px;margin-bottom:8px;">
  <div style="display:flex;justify-content:space-between;align-items:center;">
    <div style="font-family:'JetBrains Mono',monospace;font-size:13px;font-weight:700;">{escape(adv)}</div>
    <div style="font-family:'JetBrains Mono',monospace;font-size:12px;color:var(--dim,#64748b);">
      <span style="color:var(--green,#16a34a);">Halo {fmt_money(pa["halo_total"])} ({halo_p:.0f}%)</span> ·
      <span style="color:var(--red,#dc2626);">Leak {fmt_money(pa["leak_total"])} ({leak_p:.0f}%)</span>
    </div>
  </div>
  {mini_halo}{mini_leak}
</div>'''

    per_asin_section = f'''<div>
<div style="font-family:'JetBrains Mono',monospace;font-size:11px;font-weight:700;color:var(--dim,#64748b);text-transform:uppercase;letter-spacing:.08em;padding:0 0 8px;">Per-ASIN Breakdown 各 ASIN 明細</div>
{asin_sections}
</div>''' if asin_sections else ""

    return f'''<!-- HALO Panel — {label} — Generated {d} -->
<details class="panel" open style="margin-bottom:12px;">
  <summary class="panel-header" style="cursor:pointer;list-style:none;">
    <div class="panel-title"><span class="dd-arrow">&#9654;</span> HALO — {label}</div>
    <div style="font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--dim,#64748b);">{a["total_rows"]:,} rows · {a["own_asin_count"]} own ASINs · {d}</div>
  </summary>
  <div class="panel-body" style="padding:14px 18px;">
    {kpi}
    {halo_table}
    {leak_table}
    {per_asin_section}
  </div>
</details>
'''


# ── Helpers ───────────────────────────────────────────────
def _parse_args(raw_args):
    """Parse --days and brand targets from argv."""
    days = 90
    skip_next = False
    brands = []
    for i, a in enumerate(raw_args):
        if skip_next:
            skip_next = False
            continue
        if a == "--days" and i + 1 < len(raw_args):
            days = int(raw_args[i + 1])
            skip_next = True
        elif not a.startswith("--"):
            brands.append(a)
    return days, brands


def _expand_brands(brand_args):
    """Expand brand arguments (e.g. 'flux' → all 5 markets)."""
    if not brand_args:
        print("  Please specify a brand. Available:")
        print(f"    {', '.join(BRANDS.keys())}, flux")
        return []
    targets = []
    for a in brand_args:
        if a == "flux":
            targets.extend(FLUX_MARKETS)
        elif a in BRANDS:
            targets.append(a)
        else:
            print(f"  Unknown brand: {a}")
    return targets


# ── Main ─────────────────────────────────────────────────
def main():
    raw_args = sys.argv[1:]

    if not raw_args:
        print(__doc__)
        return

    command = raw_args[0]
    if command not in ("pull", "analyze", "report", "run"):
        # Backward compat: treat as brand list with full run
        command = "run"
        rest = raw_args
    else:
        rest = raw_args[1:]

    days, brand_args = _parse_args(rest)
    targets = _expand_brands(brand_args)
    if not targets:
        return

    end_date = date.today() - timedelta(days=1)
    start_date = end_date - timedelta(days=days - 1)

    for brand_key in targets:
        label = BRANDS[brand_key]["label"]

        if command == "pull":
            print(f"\n  STEP 1/3 — PULL  [{label}]")
            pull_report(brand_key, start_date, end_date)
            print(f"\n  Done. Next: python3 api/halo.py analyze {brand_key}")

        elif command == "analyze":
            print(f"\n  STEP 2/3 — ANALYZE  [{label}]")
            analyze(brand_key)
            print(f"\n  Done. Next: python3 api/halo.py report {brand_key}")

        elif command == "report":
            print(f"\n  STEP 3/3 — REPORT  [{label}]")
            out = halo_dir(brand_key)
            analysis_path = out / "halo_analysis.json"
            if not analysis_path.exists():
                print(f"  No analysis found. Run: python3 api/halo.py analyze {brand_key}")
                continue
            with open(analysis_path, encoding="utf-8") as f:
                a = json.load(f)
            html = generate_html(a)
            html_path = out / "halo_panel.html"
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html)
            print(f"  HTML: {html_path}")
            print(f"\n  Done. Panel ready at clients/{brand_key}/halo/halo_panel.html")

        elif command == "run":
            print(f"\n  FULL RUN  [{label}]  ({start_date} → {end_date})")
            data = pull_report(brand_key, start_date, end_date)
            if data:
                analyze(brand_key, data)
            print(f"\n  Done: clients/{brand_key}/halo/")


if __name__ == "__main__":
    main()
