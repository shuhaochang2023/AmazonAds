"""
Flux DE Campaign Rename — Parent by Parent
Renames campaigns to: DE {BrandName} {ModelName} {ChildASIN} {KW/ASIN/Auto} {Remark}

Usage:
  python3 api/flux_de_rename.py list                         # show all parents
  python3 api/flux_de_rename.py B08DNN39Q8                   # dry run for Avento
  python3 api/flux_de_rename.py B08DNN39Q8 --execute         # execute rename

Naming convention:
  DE ICECUBE Avento B07G8SL62W KW sonnenbrille-polarisiert
  DE ICECUBE Avento B07G8SL62W ASIN B005EG3NMC
  DE ICECUBE Avento B07G8SL62W Auto 0.55 A1
  DE 80Days PilotDB B0F1CWQCYB KW pilotenbrille-herren
  DE 80Days StrapWire B0G64L8VGX KW brillenband
"""

import os
import sys
import json
import csv
import re
import time
from pathlib import Path
from collections import defaultdict
from datetime import datetime

# ── Load .env ──
ROOT = Path(__file__).resolve().parent.parent
with open(ROOT / '.env') as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            key, val = line.split('=', 1)
            if key == 'AMAZON_ADS_CLIENT_ID': os.environ['AD_API_CLIENT_ID'] = val
            elif key == 'AMAZON_ADS_CLIENT_SECRET': os.environ['AD_API_CLIENT_SECRET'] = val
            elif key == 'AMAZON_ADS_REFRESH_TOKEN': os.environ['AD_API_REFRESH_TOKEN'] = val

DE_PROFILE = '4003401656487187'
os.environ['AD_API_PROFILE_ID'] = DE_PROFILE

from ad_api.api.sp import CampaignsV3
from ad_api.base.marketplaces import Marketplaces

MKT = 'DE'
MARKETPLACE = Marketplaces.DE
BATCH_SIZE = 50
THROTTLE = 1.0
ASIN_RE = re.compile(r'(B0[A-Z0-9]{8,10})')

# ══════════════════════════════════════════════════════════════
# PRODUCT MAP from Products.csv
# ══════════════════════════════════════════════════════════════
CHILD_TO_PARENT = {}
CHILD_TO_MODEL = {}
PARENT_TO_NAME = {}
PARENT_TO_BRAND = {}
PARENT_CHILDREN = defaultdict(list)


def load_products():
    products_csv = ROOT / 'clients' / 'flux' / 'input' / 'de' / 'Products.csv'
    with open(products_csv, encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            parent = row.get('Parent ASIN', '').strip()
            asin = row.get('ASIN', '').strip()
            title = row.get('Title', '').strip()
            sku = row.get('SKU', '')
            t = title.upper()

            # Determine model name
            if 'AVENTO' in t: short = 'Avento'
            elif 'SPORTECH' in t: short = 'Sportech'
            elif 'VERANO' in t: short = 'Verano'
            elif 'VENTURA' in t: short = 'Ventura'
            elif 'DYNAMIC' in t: short = 'Dynamic'
            elif 'JET II' in t or 'JETII' in t: short = 'JetIINeo'
            elif 'CARMEL' in t: short = 'Carmel'
            elif 'HYPERBOLIC' in t: short = 'Hyperbolic'
            elif 'SPRINT' in t: short = 'Sprint'
            elif 'LASO' in t: short = 'Laso17'
            elif 'PILOTENBRILLE' in t or 'AV101' in sku: short = 'PilotDB'
            elif 'RUNDE' in t or 'RD101' in sku: short = 'RoundDB'
            elif 'ECKIGE' in t and 'CL102' in sku: short = 'ClassicDB2'
            elif 'ECKIGE' in t or 'CL101' in sku: short = 'ClassicDB'
            elif 'GEOMETRISCH' in t or 'LD101' in sku: short = 'LadyGeo'
            elif 'OVAL' in t or 'LD102' in sku: short = 'LadyOval'
            elif 'STRAP' in t and ('102' in sku or 'WIRE' in t.upper()): short = 'StrapWire'
            elif 'STRAP' in t or 'BRILLENBAND' in t: short = 'StrapNylon'
            else: short = title[:20].replace(' ', '')

            # Determine brand
            if '80DAYS' in t or '80 DAYS' in t:
                brand = '80Days'
            elif 'ICECUBE' in t or 'ICE CUBE' in t or 'ICEBUBE' in t:
                brand = 'ICECUBE'
            else:
                brand = 'ICECUBE'  # default for Flux DE

            if parent and asin:
                CHILD_TO_PARENT[asin] = parent
                CHILD_TO_MODEL[asin] = short
                PARENT_CHILDREN[parent].append(asin)

                existing = PARENT_TO_NAME.get(parent, '')
                KNOWN = ('Verano', 'Avento', 'Sportech', 'Ventura', 'Dynamic',
                         'JetIINeo', 'Carmel', 'Hyperbolic', 'Sprint', 'Laso17',
                         'PilotDB', 'RoundDB', 'ClassicDB', 'ClassicDB2',
                         'LadyGeo', 'LadyOval', 'StrapWire', 'StrapNylon')
                is_known = short in KNOWN
                if not existing or (existing not in KNOWN and is_known):
                    PARENT_TO_NAME[parent] = short
                    PARENT_TO_BRAND[parent] = brand


# ══════════════════════════════════════════════════════════════
# PARSE OLD CAMPAIGN NAME → NEW NAME
# ══════════════════════════════════════════════════════════════
def build_new_name(old_name, child_asin, model, brand):
    """
    Convert old campaign name to: DE {Brand} {Model} {ASIN} {Type} {Remark}
    """
    nl = old_name.lower()

    # ── Already renamed? Skip if starts with "DE ICECUBE" or "DE 80Days" ──
    if old_name.startswith('DE ICECUBE ') or old_name.startswith('DE 80Days '):
        return None  # already in new format

    # ── Partially renamed: "DE {Model} ..." — just insert brand ──
    KNOWN_MODELS = ('Avento', 'Sportech', 'Verano', 'Ventura', 'Dynamic',
                    'JetIINeo', 'Carmel', 'Hyperbolic', 'Sprint', 'Laso17',
                    'PilotDB', 'RoundDB', 'ClassicDB', 'ClassicDB2',
                    'LadyGeo', 'LadyOval', 'StrapWire', 'StrapNylon')
    for km in KNOWN_MODELS:
        if old_name.startswith(f'DE {km} '):
            rest = old_name[len(f'DE {km} '):]
            return f"DE {brand} {model} {rest}"

    # ── Pattern: "DE AVENTO SUNGLASSES A#_ {ASIN1} - {ASIN2}" ──
    m = re.match(r'DE AVENTO SUNGLASS\w* A(\d+)[_ ]+(\w+)\s*-\s*(\w+)', old_name)
    if m:
        a_num = m.group(1)
        asin1 = m.group(2)
        asin2 = m.group(3)
        return f"DE {brand} {model} {asin1} ASIN {asin2} A{a_num}"

    # ── Pattern: "DE Sunglasses ... MBA SP-PT {desc} {ASIN1} {ASIN2}" ──
    m_pt = re.match(r'DE Sunglasses .+ SP-PT (.+?)\s+(B0\w+)\s+(B0\w+)', old_name)
    if m_pt:
        desc = m_pt.group(1).replace(' ', '-')
        asin1 = m_pt.group(2)
        asin2 = m_pt.group(3)
        return f"DE {brand} {model} {asin1} ASIN {asin2} PT-{desc}"

    # ── Pattern: Conquest ──
    if 'conquest' in nl:
        m2 = re.search(r'Conquest\s+(.+?)\s+to\s+.+?\s+(B0\w+)\s+(B0\w+)', old_name)
        if m2:
            competitor = m2.group(1).replace(' ', '-')
            return f"DE {brand} {model} {m2.group(3)} ASIN {m2.group(2)} Conquest-{competitor}"

    # ── Pattern: Auto campaigns (must have "Bulk Auto", not just "auto" in a keyword) ──
    if 'bulk auto' in nl:
        # "... A# - Bulk Auto {bid} - {date}"
        m3 = re.search(r'A(\d+)\s*-\s*Bulk Auto\s*([\d,\.]+)', old_name)
        if m3:
            bid = m3.group(2).replace(',', '.')
            return f"DE {brand} {model} {child_asin} Auto {bid} A{m3.group(1)}"
        # "... - Bulk Auto A# {bid} - {date}"
        m3b = re.search(r'Bulk Auto A(\d+)\s*([\d,\.]+)', old_name)
        if m3b:
            bid = m3b.group(2).replace(',', '.')
            return f"DE {brand} {model} {child_asin} Auto {bid} A{m3b.group(1)}"
        # Generic auto
        m3c = re.search(r'Auto\s*([\d,\.]+)', old_name)
        if m3c:
            bid = m3c.group(1).replace(',', '.')
            return f"DE {brand} {model} {child_asin} Auto {bid}"
        return f"DE {brand} {model} {child_asin} Auto"

    # ── Pattern: Manual with " - {target}" at end ──
    # e.g. "Sonnenbrillen für Herren B07G8SL62W Avento - sonnenbrille polarisiert"
    # e.g. "Sportsonnenbrillen für Damen B07CNKVWQP A1- b00m852hm4"
    m4 = re.search(r'(?:A\d+\s*)?[-–]\s*(.+)$', old_name)
    if m4:
        target = m4.group(1).strip()
        # Extract A# if present before the dash
        a_match = re.search(r'A(\d+)\s*[-–]', old_name)
        a_suffix = f" A{a_match.group(1)}" if a_match else ""

        # Is target an ASIN?
        if re.match(r'[Bb]0[A-Za-z0-9]{8,}', target):
            return f"DE {brand} {model} {child_asin} ASIN {target.upper()}{a_suffix}"
        else:
            kw_clean = target.replace(' ', '-')
            # Truncate to keep under 128 chars
            max_kw = 128 - len(f"DE {brand} {model} {child_asin} KW {a_suffix}")
            kw_clean = kw_clean[:max_kw]
            return f"DE {brand} {model} {child_asin} KW {kw_clean}{a_suffix}"

    # ── Pattern: "DE {something} {ASIN} KW ..." (already partly renamed) ──
    m5 = re.match(r'DE\s+\w+\s+(B0\w+)\s+KW\s+(.+)', old_name)
    if m5:
        kw = m5.group(2).strip()
        return f"DE {brand} {model} {child_asin} KW {kw}"

    # ── Pattern: "{Category} {ASIN} ..." with number suffix ──
    # e.g. "80Days_Straps_B0G64L8VGX - Bulk Auto A1 0,41 - 20-Feb-26"
    m6 = re.search(r'Bulk Auto A(\d+)\s*([\d,\.]+)', old_name)
    if m6:
        bid = m6.group(2).replace(',', '.')
        return f"DE {brand} {model} {child_asin} Auto {bid} A{m6.group(1)}"

    # ── Fallback: keep old name but prefix with standard format ──
    return None


# ══════════════════════════════════════════════════════════════
# API
# ══════════════════════════════════════════════════════════════
def list_all_campaigns():
    api = CampaignsV3(marketplace=MARKETPLACE)
    all_camps = []
    next_token = None
    while True:
        body = {"maxResults": 100}
        if next_token:
            body["nextToken"] = next_token
        result = api.list_campaigns(body=json.dumps(body))
        payload = result.payload
        if isinstance(payload, dict):
            camps = payload.get('campaigns', [])
            next_token = payload.get('nextToken')
        elif isinstance(payload, list):
            camps = payload
            next_token = None
        else:
            break
        all_camps.extend(camps)
        if not next_token:
            break
        time.sleep(0.3)
    return all_camps


def match_to_parent(campaign):
    name = campaign.get('name', '')
    for asin in ASIN_RE.findall(name):
        if asin in CHILD_TO_PARENT:
            return CHILD_TO_PARENT[asin], asin
        if asin in PARENT_TO_NAME:
            return asin, asin
    return None, None


def rename_campaigns(renames, dry_run=True):
    """Execute renames via API. renames = list of (campaignId, newName)"""
    if dry_run:
        print("\n  [DRY RUN] No changes made.")
        return 0, 0

    api = CampaignsV3(marketplace=MARKETPLACE)
    total_ok = 0
    total_err = 0

    for i in range(0, len(renames), BATCH_SIZE):
        batch = renames[i:i+BATCH_SIZE]
        body = {
            "campaigns": [
                {"campaignId": str(cid), "name": new_name}
                for cid, new_name in batch
            ]
        }
        batch_num = i // BATCH_SIZE + 1
        total_batches = (len(renames) + BATCH_SIZE - 1) // BATCH_SIZE

        try:
            result = api.edit_campaigns(body=json.dumps(body))
            payload = result.payload
            if isinstance(payload, dict):
                cr = payload.get('campaigns', payload)
                success = cr.get('success', []) if isinstance(cr, dict) else []
                errors = cr.get('error', []) if isinstance(cr, dict) else []
                ok = len(success) if isinstance(success, list) else len(batch)
                err = len(errors) if isinstance(errors, list) else 0
                total_ok += ok
                total_err += err
                if errors and isinstance(errors, list):
                    for e in errors[:3]:
                        print(f"    ERR: {e}")
            else:
                total_ok += len(batch)
            print(f"    batch {batch_num}/{total_batches}: {len(batch)} sent")
        except Exception as e:
            total_err += len(batch)
            print(f"    batch {batch_num}/{total_batches}: FAILED — {e}")

        time.sleep(THROTTLE)

    print(f"\n  Rename complete: {total_ok} OK, {total_err} errors")
    return total_ok, total_err


# ══════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════
def main():
    load_products()

    if len(sys.argv) < 2:
        print("Usage: python3 api/flux_de_rename.py <parent_asin|list> [--execute]")
        sys.exit(1)

    if sys.argv[1] == 'list':
        print(f"\n  DE Parents ({len(PARENT_TO_NAME)}):")
        for p in sorted(PARENT_TO_NAME.keys(), key=lambda x: PARENT_TO_NAME[x]):
            name = PARENT_TO_NAME[p]
            brand = PARENT_TO_BRAND.get(p, '?')
            children = PARENT_CHILDREN.get(p, [])
            print(f"    {p}  {brand:10s} {name:15s}  ({len(children)} children)")
        sys.exit(0)

    target_parent = sys.argv[1].upper()
    do_execute = '--execute' in sys.argv

    if target_parent not in PARENT_TO_NAME:
        if target_parent in CHILD_TO_PARENT:
            target_parent = CHILD_TO_PARENT[target_parent]
        else:
            print(f"  Unknown ASIN: {target_parent}")
            print(f"  Run with 'list' to see all parents.")
            sys.exit(1)

    product = PARENT_TO_NAME[target_parent]
    brand = PARENT_TO_BRAND.get(target_parent, 'ICECUBE')
    children = set(PARENT_CHILDREN.get(target_parent, []))
    children.add(target_parent)

    print("=" * 70)
    print(f"  DE RENAME — {brand} {product} ({target_parent})")
    print(f"  Format: DE {brand} {product} {{ASIN}} {{KW/ASIN/Auto}} {{Remark}}")
    print(f"  Children: {', '.join(sorted(children))}")
    print(f"  Mode: {'EXECUTE' if do_execute else 'DRY RUN'}")
    print("=" * 70)

    # Load campaigns from API
    print("\n  Loading campaigns from API...")
    all_campaigns = list_all_campaigns()
    active = [c for c in all_campaigns if c.get('state', '').upper() != 'ARCHIVED']
    print(f"  Total: {len(all_campaigns)} ({len(active)} non-archived)")

    # Filter to this parent's campaigns
    parent_camps = []
    for c in active:
        p, child_asin = match_to_parent(c)
        if p == target_parent:
            parent_camps.append((c, child_asin))

    print(f"  Matched to {product}: {len(parent_camps)} campaigns")

    if not parent_camps:
        print("  No campaigns found for this parent.")
        sys.exit(0)

    # Build rename plan
    renames = []
    seen_names = {}

    print(f"\n{'─' * 70}")
    print(f"  RENAME PLAN — {brand} {product}")
    print(f"{'─' * 70}")

    by_child = defaultdict(list)
    for c, child_asin in parent_camps:
        by_child[child_asin].append(c)

    for child_asin in sorted(by_child.keys()):
        camps = by_child[child_asin]
        model = CHILD_TO_MODEL.get(child_asin, product)
        print(f"\n  {child_asin} ({len(camps)} campaigns)")

        for c in sorted(camps, key=lambda x: x.get('name', '')):
            old_name = c.get('name', '')
            cid = c.get('campaignId', '')
            state = c.get('state', '').upper()

            new_name = build_new_name(old_name, child_asin, model, brand)

            if new_name is None:
                print(f"    ⏭️  SKIP (already clean): {old_name[:70]}")
                continue

            # Deduplicate
            if new_name in seen_names:
                seen_names[new_name] += 1
                new_name = f"{new_name} #{seen_names[new_name]}"
            else:
                seen_names[new_name] = 1

            # Truncate to 128 chars (Amazon limit)
            if len(new_name) > 128:
                new_name = new_name[:128]

            renames.append((cid, new_name))

            state_icon = '🟢' if state == 'ENABLED' else '⏸️'
            print(f"    {state_icon} {old_name[:65]}")
            print(f"       → {new_name}")

    # Summary
    print(f"\n{'─' * 70}")
    print(f"  SUMMARY: {len(renames)} campaigns to rename")
    print(f"{'─' * 70}")

    # Save CSV log
    out_dir = ROOT / 'clients' / 'flux' / 'bulk-output'
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M')
    csv_path = out_dir / f'DE_rename_{product}_{timestamp}.csv'
    with open(csv_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['campaignId', 'oldName', 'newName'])
        for cid, new_name in renames:
            old = next((c.get('name', '') for c, _ in parent_camps if str(c.get('campaignId', '')) == str(cid)), '')
            writer.writerow([cid, old, new_name])
    print(f"  Log: {csv_path.name}")

    # Execute or dry run
    if do_execute and renames:
        print(f"\n  Executing {len(renames)} renames via API...")
        rename_campaigns(renames, dry_run=False)
    elif renames:
        print(f"\n  [DRY RUN] Review above, then re-run with --execute")
    else:
        print(f"\n  All campaigns already have correct names.")


if __name__ == '__main__':
    main()
