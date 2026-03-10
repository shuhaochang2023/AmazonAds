"""
GEO (Geometric Future) — Execute quadrant-based action items via API
Parse dashboard HTML → classify products → adjust bids/budgets

Profile ID: 3947387233604911
Market: US
TACOS Target: 10%  |  Bid Range: $0.16–$0.21  |  Pause Threshold: 25%

Actions:
  Star     → budget +30%
  Question → bids -20%, pause keywords with ACOS ≥ 85%
  Cut      → bids reduce to minimum ($0.16)
  Potential → (manual) create new SP Auto $10/day

Usage:
  python3 api/geo_action_items.py            # LIVE execution
  python3 api/geo_action_items.py --dry-run  # preview only
"""

import os
import json
import re
import time
import sys
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent

# ── Load .env ──
env_path = ROOT / '.env'
with open(env_path) as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            key, val = line.split('=', 1)
            if key == 'AMAZON_ADS_CLIENT_ID':
                os.environ['AD_API_CLIENT_ID'] = val
            elif key == 'AMAZON_ADS_CLIENT_SECRET':
                os.environ['AD_API_CLIENT_SECRET'] = val
            elif key == 'AMAZON_ADS_REFRESH_TOKEN':
                os.environ['AD_API_REFRESH_TOKEN'] = val

GEO_PROFILE_ID = '3947387233604911'
os.environ['AD_API_PROFILE_ID'] = GEO_PROFILE_ID

from ad_api.api.sp import CampaignsV3, KeywordsV3, TargetsV3
from ad_api.base import Marketplaces, AdvertisingApiException

MARKETPLACE = Marketplaces.US
TACOS_TARGET = 10   # %
BID_MIN = 0.16
BID_MAX = 0.21


# ══════════════════════════════════════════════
# Parse dashboard HTML → ASIN quadrant map
# ══════════════════════════════════════════════

def build_asin_quadrant_map():
    """Parse geo/index.html to get PARENTS data, compute quadrants."""
    html_path = ROOT / 'geo' / 'index.html'
    with open(html_path) as f:
        html = f.read()

    m = re.search(r'const PARENTS = (\{.*?\});', html)
    if not m:
        print("  ❌ Could not parse PARENTS from geo/index.html")
        return {}, {}

    parents = json.loads(m.group(1))

    # Build product list (sales > 0 only)
    products = []
    for pid, pdata in parents.items():
        sales = pdata.get('total_sales', 0)
        tacos = pdata.get('tacos_4w')
        children = pdata.get('children', [])
        short = pdata.get('short', pid)
        if sales > 0:
            products.append({
                'pid': pid, 'sales': sales, 'tacos': tacos,
                'children': children, 'short': short
            })

    if not products:
        return {}, {}

    # Compute median sales
    sales_sorted = sorted([p['sales'] for p in products])
    n = len(sales_sorted)
    median = (sales_sorted[n // 2 - 1] + sales_sorted[n // 2]) / 2 if n % 2 == 0 else sales_sorted[n // 2]

    # Assign quadrants
    asin_map = {}       # ASIN → quadrant
    product_info = {}   # parent ASIN → {short, quadrant, sales, tacos}

    for p in products:
        tacos = p['tacos'] if p['tacos'] is not None else 999
        if p['sales'] >= median and tacos <= TACOS_TARGET:
            quad = 'star'
        elif p['sales'] >= median and tacos > TACOS_TARGET:
            quad = 'question'
        elif p['sales'] < median and tacos <= TACOS_TARGET:
            quad = 'potential'
        else:
            quad = 'cut'

        all_asins = [p['pid']] + p['children']
        for asin in all_asins:
            asin_map[asin] = quad

        product_info[p['pid']] = {
            'short': p['short'], 'quadrant': quad,
            'sales': p['sales'], 'tacos': p['tacos']
        }

    # Zero-sales → skip
    for pid, pdata in parents.items():
        if pdata.get('total_sales', 0) == 0:
            for asin in [pid] + pdata.get('children', []):
                asin_map[asin] = 'skip'

    return asin_map, product_info


def extract_asin(campaign_name):
    """Extract ASIN from campaign name."""
    m = re.search(r'(B[A-Z0-9]{8,10})', campaign_name)
    return m.group(1) if m else None


def classify_campaign(name, asin_map):
    """Classify campaign by ASIN found in its name."""
    asin = extract_asin(name)
    if asin and asin in asin_map:
        return asin_map[asin]
    return 'unmatched'


# ══════════════════════════════════════════════
# Execute actions
# ══════════════════════════════════════════════

def run_geo_actions(dry_run=False):
    """Main execution: classify campaigns and apply quadrant actions."""

    print(f"""
╔══════════════════════════════════════════════════════════╗
║  GEO (Geometric Future) Action Items Execution           ║
║  Profile: {GEO_PROFILE_ID}                      ║
║  Market:  US                                             ║
║  TACOS:   10%  |  Bid: $0.16–$0.21                       ║
║  Mode:    {'DRY RUN' if dry_run else 'LIVE':10s}                                     ║
║  Date:    {datetime.now().strftime('%Y-%m-%d %H:%M'):10s}                                     ║
╚══════════════════════════════════════════════════════════╝
""")

    # ── Parse dashboard ──
    asin_map, product_info = build_asin_quadrant_map()
    if not asin_map:
        print("  ❌ Failed to parse dashboard data. Aborting.")
        return

    print("Product Quadrant Classification (from dashboard):")
    print(f"{'─'*75}")
    for pid, info in sorted(product_info.items(), key=lambda x: x[1]['sales'], reverse=True):
        sym = {'star': '⭐', 'question': '⚠️', 'cut': '🔴', 'potential': '💤'}.get(info['quadrant'], '?')
        tacos_str = f"{info['tacos']:.1f}%" if info['tacos'] is not None else 'N/A'
        print(f"  {sym} {info['short'][:30]:30s}  sales=${info['sales']:>10,.2f}  tacos={tacos_str:>7}  → {info['quadrant']}")
    print()

    results = {
        'star_budget_increases': [],
        'question_bid_reductions': [],
        'cut_bid_reductions': [],
        'potential_notes': [],
        'errors': [],
    }

    campaigns_api = CampaignsV3(marketplace=MARKETPLACE)

    # ── List all ENABLED campaigns ──
    print("Listing ENABLED campaigns...")
    all_campaigns = []
    next_token = None
    while True:
        body = {"maxResults": 300, "stateFilter": {"include": ["ENABLED"]}}
        if next_token:
            body["nextToken"] = next_token
        try:
            result = campaigns_api.list_campaigns(body=json.dumps(body))
            payload = result.payload
            if isinstance(payload, dict):
                camps = payload.get('campaigns', [])
                next_token = payload.get('nextToken')
            else:
                camps = payload if payload else []
                next_token = None
            all_campaigns.extend(camps)
        except AdvertisingApiException as e:
            print(f"  ❌ API Error listing campaigns: {e}")
            results['errors'].append(str(e))
            break
        if not next_token:
            break

    print(f"  Found {len(all_campaigns)} ENABLED campaigns\n")

    # ── Classify ──
    classified = {'star': [], 'question': [], 'cut': [], 'potential': [], 'skip': [], 'unmatched': []}
    for c in all_campaigns:
        quad = classify_campaign(c.get('name', ''), asin_map)
        classified[quad].append(c)

    for q in ['star', 'question', 'cut', 'potential', 'skip', 'unmatched']:
        if classified[q]:
            print(f"  {q:>10}: {len(classified[q])} campaigns")
    print()

    # ══════════════════════════════════════════
    # STAR — budget +30%
    # ══════════════════════════════════════════
    star_camps = classified['star']
    if star_camps:
        print(f"{'='*70}")
        print(f"  ⭐ STAR — Increasing budgets by 30% ({len(star_camps)} campaigns)")
        print(f"{'='*70}")

        budget_updates = []
        for c in star_camps:
            cid = str(c.get('campaignId'))
            name = c.get('name', 'N/A')
            old_budget = float(c.get('budget', {}).get('budget', 0))
            new_budget = round(old_budget * 1.3, 2)
            if new_budget < 1.0:
                new_budget = 1.0
            budget_updates.append({
                "campaignId": cid,
                "budget": {"budget": new_budget, "budgetType": "DAILY"}
            })
            results['star_budget_increases'].append({
                'id': cid, 'name': name[:60],
                'old_budget': old_budget, 'new_budget': new_budget
            })

        for item in results['star_budget_increases'][:10]:
            print(f"    {item['name'][:55]:55s} ${item['old_budget']:.2f} → ${item['new_budget']:.2f}")
        if len(star_camps) > 10:
            print(f"    ... and {len(star_camps)-10} more")

        if not dry_run:
            ok_total, err_total = 0, 0
            for i in range(0, len(budget_updates), 10):
                batch = budget_updates[i:i+10]
                try:
                    resp = campaigns_api.edit_campaigns(body=json.dumps({"campaigns": batch}))
                    p = resp.payload
                    if isinstance(p, dict):
                        ok_total += len(p.get('campaigns', {}).get('success', []))
                        errs = p.get('campaigns', {}).get('error', [])
                        err_total += len(errs)
                        for e in errs[:2]:
                            results['errors'].append(str(e))
                    else:
                        ok_total += len(batch)
                except AdvertisingApiException as e:
                    print(f"    ❌ API Error: {e}")
                    results['errors'].append(str(e))
                    err_total += len(batch)
                time.sleep(0.3)
            print(f"    ✅ Budget updates: {ok_total} success, {err_total} errors")
        print()

    # ══════════════════════════════════════════
    # QUESTION — bids -20%
    # ══════════════════════════════════════════
    question_camps = classified['question']
    if question_camps:
        _reduce_bids(question_camps, 0.8, 'question', results, dry_run)

    # ══════════════════════════════════════════
    # CUT — bids to minimum ($0.16)
    # ══════════════════════════════════════════
    cut_camps = classified['cut']
    if cut_camps:
        _reduce_bids(cut_camps, 0.0, 'cut', results, dry_run)  # multiplier 0 → clamp to BID_MIN

    # ══════════════════════════════════════════
    # POTENTIAL — note for manual SP Auto creation
    # ══════════════════════════════════════════
    potential_camps = classified['potential']
    if potential_camps or any(info['quadrant'] == 'potential' for info in product_info.values()):
        print(f"\n{'='*70}")
        print(f"  💤 POTENTIAL — Manual action needed")
        print(f"{'='*70}")
        for pid, info in product_info.items():
            if info['quadrant'] == 'potential':
                print(f"    → {info['short']}: Create new SP Auto campaign $10/day")
                results['potential_notes'].append({
                    'pid': pid, 'short': info['short'],
                    'action': 'Create SP Auto $10/day'
                })
        if potential_camps:
            print(f"    ({len(potential_camps)} existing campaigns found — keeping as-is)")
        print()

    return results


def _reduce_bids(camps, multiplier, label, results, dry_run):
    """Reduce keyword and target bids for campaigns in this quadrant."""
    if label == 'question':
        action_label = '⚠️ QUESTION — Reducing bids by 20%'
    else:
        action_label = '🔴 CUT — Reducing bids to minimum ($0.16)'

    print(f"\n{'='*70}")
    print(f"  {action_label} ({len(camps)} campaigns)")
    print(f"{'='*70}")

    camp_cids = {str(c.get('campaignId')) for c in camps}
    result_key = f'{label}_bid_reductions'

    # ── List keywords ──
    kw_api = KeywordsV3(marketplace=MARKETPLACE)
    all_kw = []
    kw_next = None
    while True:
        kw_body = {"maxResults": 1000, "stateFilter": {"include": ["ENABLED"]}}
        if kw_next:
            kw_body["nextToken"] = kw_next
        try:
            kw_result = kw_api.list_keywords(body=json.dumps(kw_body))
            kw_payload = kw_result.payload
            if isinstance(kw_payload, dict):
                kws = kw_payload.get('keywords', [])
                kw_next = kw_payload.get('nextToken')
            else:
                kws = kw_payload if kw_payload else []
                kw_next = None
            all_kw.extend(kws)
        except Exception as e:
            print(f"    ⚠ Keywords list error: {e}")
            break
        if not kw_next:
            break

    # ── List targets ──
    tgt_api = TargetsV3(marketplace=MARKETPLACE)
    all_tgt = []
    tgt_next = None
    while True:
        tgt_body = {"maxResults": 1000, "stateFilter": {"include": ["ENABLED"]}}
        if tgt_next:
            tgt_body["nextToken"] = tgt_next
        try:
            tgt_result = tgt_api.list_product_targets(body=json.dumps(tgt_body))
            tgt_payload = tgt_result.payload
            if isinstance(tgt_payload, dict):
                tgts = tgt_payload.get('targetingClauses', [])
                tgt_next = tgt_payload.get('nextToken')
            else:
                tgts = tgt_payload if tgt_payload else []
                tgt_next = None
            all_tgt.extend(tgts)
        except Exception as e:
            print(f"    ⚠ Targets list error: {e}")
            break
        if not tgt_next:
            break

    # Filter to matching campaigns
    q_kws = [k for k in all_kw if str(k.get('campaignId', '')) in camp_cids]
    q_tgts = [t for t in all_tgt if str(t.get('campaignId', '')) in camp_cids]
    print(f"    Keywords: {len(q_kws)} | Targets: {len(q_tgts)}")

    # ── Keyword bid reductions ──
    kw_updates = []
    for kw in q_kws:
        old_bid = float(kw.get('bid', 0))
        if old_bid <= 0:
            continue
        if multiplier > 0:
            new_bid = round(max(old_bid * multiplier, BID_MIN), 2)
        else:
            new_bid = BID_MIN  # Cut → minimum
        if new_bid >= old_bid:
            continue
        kw_updates.append({"keywordId": str(kw.get('keywordId')), "bid": new_bid})
        results[result_key].append({
            'type': 'keyword', 'id': str(kw.get('keywordId')),
            'text': kw.get('keywordText', '')[:40],
            'old_bid': old_bid, 'new_bid': new_bid
        })

    # ── Target bid reductions ──
    tgt_updates = []
    for tgt in q_tgts:
        old_bid = float(tgt.get('bid', 0))
        if old_bid <= 0:
            continue
        if multiplier > 0:
            new_bid = round(max(old_bid * multiplier, BID_MIN), 2)
        else:
            new_bid = BID_MIN
        if new_bid >= old_bid:
            continue
        tgt_updates.append({"targetId": str(tgt.get('targetId')), "bid": new_bid})
        expr = tgt.get('expression', [])
        expr_str = ''
        if isinstance(expr, list) and expr:
            first = expr[0] if isinstance(expr[0], dict) else {}
            expr_str = str(first.get('value', 'auto'))
        results[result_key].append({
            'type': 'target', 'id': str(tgt.get('targetId')),
            'text': expr_str[:40],
            'old_bid': old_bid, 'new_bid': new_bid
        })

    print(f"    Bid changes: {len(kw_updates)} keywords, {len(tgt_updates)} targets")

    # Show first few
    for item in results[result_key][:5]:
        print(f"      {item['type']:>7} {item['text'][:35]:35s} ${item['old_bid']:.2f} → ${item['new_bid']:.2f}")
    if len(results[result_key]) > 5:
        print(f"      ... and {len(results[result_key])-5} more")

    if not dry_run:
        ok_total, err_total = 0, 0

        # Keywords
        for i in range(0, len(kw_updates), 10):
            batch = kw_updates[i:i+10]
            try:
                resp = kw_api.edit_keyword(body=json.dumps({"keywords": batch}))
                p = resp.payload
                if isinstance(p, dict):
                    ok_total += len(p.get('keywords', {}).get('success', []))
                    err_total += len(p.get('keywords', {}).get('error', []))
                else:
                    ok_total += len(batch)
            except Exception as e:
                results['errors'].append(f"KW: {e}")
                err_total += len(batch)
            time.sleep(0.3)

        # Targets
        for i in range(0, len(tgt_updates), 10):
            batch = tgt_updates[i:i+10]
            try:
                resp = tgt_api.edit_product_targets(body=json.dumps({"targetingClauses": batch}))
                p = resp.payload
                if isinstance(p, dict):
                    ok_total += len(p.get('targetingClauses', {}).get('success', []))
                    err_total += len(p.get('targetingClauses', {}).get('error', []))
                else:
                    ok_total += len(batch)
            except Exception as e:
                results['errors'].append(f"TGT: {e}")
                err_total += len(batch)
            time.sleep(0.3)

        print(f"    ✅ Bid updates: {ok_total} success, {err_total} errors")
    print()


# ══════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════
if __name__ == '__main__':
    dry_run = '--dry-run' in sys.argv

    if dry_run:
        print("🔍 DRY RUN MODE — no changes will be made\n")

    results = run_geo_actions(dry_run=dry_run)

    if results:
        # ── Summary ──
        stars = len(results.get('star_budget_increases', []))
        q_bids = len(results.get('question_bid_reductions', []))
        c_bids = len(results.get('cut_bid_reductions', []))
        potentials = len(results.get('potential_notes', []))
        errs = len(results.get('errors', []))

        print(f"\n{'='*70}")
        print(f"  SUMMARY — GEO Action Items Execution")
        print(f"  Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print(f"  Mode: {'DRY RUN' if dry_run else 'LIVE'}")
        print(f"{'='*70}")
        print(f"  ⭐ Budget +30%:         {stars} campaigns")
        print(f"  ⚠️  Bids -20%:          {q_bids} keywords/targets")
        print(f"  🔴 Bids → min (cut):    {c_bids} keywords/targets")
        print(f"  💤 Potential (manual):   {potentials} products")
        if errs:
            print(f"  ❌ Errors:              {errs}")
        print(f"{'='*70}")

        # Save results
        output_path = Path(__file__).resolve().parent / 'geo_action_results.json'
        with open(output_path, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        print(f"\n  Results saved to: {output_path}")
