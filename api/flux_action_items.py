"""
Flux — Execute action items across all 5 marketplaces
ASIN-based classification from dashboard data:
  Star → budget +30%
  Question → bids -20%
  Cut → bids reduce to minimum (0.10)

Profile IDs:
  AU: 3601686309797276  |  US: 3255856020251415  |  CA: 599373744640869
  UK: 2347387401732870  |  DE: 4003401656487187
"""

import os
import json
import re
import time
import sys
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent

# Load .env
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

from ad_api.api.sp import CampaignsV3, KeywordsV3, TargetsV3
from ad_api.base import Marketplaces, AdvertisingApiException

# ══════════════════════════════════════════════
# Parse dashboard HTML to build ASIN → quadrant maps
# ══════════════════════════════════════════════

TACOS_TARGET = 30  # all markets

MARKET_CONFIG = {
    'AU': {'profile_id': '3601686309797276', 'marketplace': Marketplaces.AU, 'currency': 'A$', 'html': 'au.html'},
    'US': {'profile_id': '3255856020251415', 'marketplace': Marketplaces.US, 'currency': '$', 'html': 'us.html'},
    'CA': {'profile_id': '599373744640869', 'marketplace': Marketplaces.CA, 'currency': 'CA$', 'html': 'ca.html'},
    'UK': {'profile_id': '2347387401732870', 'marketplace': Marketplaces.UK, 'currency': '£', 'html': 'uk.html'},
    'DE': {'profile_id': '4003401656487187', 'marketplace': Marketplaces.DE, 'currency': '€', 'html': 'de.html'},
}

BID_MIN = 0.10


def build_asin_quadrant_map(html_file):
    """Parse HTML to get parent products, compute quadrants, return ASIN→quadrant map."""
    with open(ROOT / 'flux' / html_file) as f:
        html = f.read()

    m = re.search(r'const PARENTS = (\{.*?\});', html)
    if not m:
        return {}, {}
    parents = json.loads(m.group(1))

    # Build product list with sales > 0
    products = []
    for pid, pdata in parents.items():
        sales = pdata.get('total_sales', 0)
        tacos = pdata.get('tacos_4w')
        children = pdata.get('children', [])
        short = pdata.get('short', pid)
        if sales > 0:
            products.append({'pid': pid, 'sales': sales, 'tacos': tacos, 'children': children, 'short': short})

    if not products:
        return {}, {}

    # Compute median
    sales_sorted = sorted([p['sales'] for p in products])
    n = len(sales_sorted)
    median = (sales_sorted[n//2-1] + sales_sorted[n//2]) / 2 if n % 2 == 0 else sales_sorted[n//2]

    # Assign quadrants
    asin_map = {}  # ASIN → quadrant
    product_info = {}  # ASIN → {short, quadrant, sales, tacos}
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

        # Map parent + all children to this quadrant
        all_asins = [p['pid']] + p['children']
        for asin in all_asins:
            asin_map[asin] = quad
        product_info[p['pid']] = {
            'short': p['short'], 'quadrant': quad,
            'sales': p['sales'], 'tacos': p['tacos']
        }

    # Zero-sales products → skip (no action needed)
    for pid, pdata in parents.items():
        if pdata.get('total_sales', 0) == 0:
            for asin in [pid] + pdata.get('children', []):
                asin_map[asin] = 'skip'

    return asin_map, product_info


def extract_asin(campaign_name):
    """Extract ASIN from campaign name (usually at the start)."""
    m = re.search(r'(B[A-Z0-9]{8,10})', campaign_name)
    return m.group(1) if m else None


def classify_campaign(name, asin_map):
    """Classify campaign by ASIN found in its name."""
    asin = extract_asin(name)
    if asin and asin in asin_map:
        return asin_map[asin]
    return 'unmatched'


def process_market(market_code, config, dry_run=False):
    """Process one marketplace — apply quadrant-based actions."""
    profile_id = config['profile_id']
    os.environ['AD_API_PROFILE_ID'] = profile_id

    print(f"\n{'='*70}")
    print(f"  {market_code} Market — Profile {profile_id}")
    print(f"{'='*70}")

    # Build ASIN → quadrant map from dashboard data
    asin_map, product_info = build_asin_quadrant_map(config['html'])
    if not asin_map:
        print("  ⚠ Could not parse dashboard data, skipping")
        return {'market': market_code, 'error': 'parse failed'}

    # Print product quadrant assignments
    print(f"\n  Product quadrants (from dashboard):")
    for pid, info in sorted(product_info.items(), key=lambda x: x[1]['sales'], reverse=True):
        sym = {'star': '⭐', 'question': '⚠️', 'cut': '🔴', 'potential': '💤'}.get(info['quadrant'], '?')
        print(f"    {sym} {info['short'][:40]:40s} sales={config['currency']}{info['sales']:>10,.2f}  tacos={str(info['tacos']):>6s}  → {info['quadrant']}")

    campaigns_api = CampaignsV3(marketplace=config['marketplace'])

    # ── Step 1: List all ENABLED campaigns ──
    all_campaigns = []
    next_token = None
    while True:
        body = {"maxResults": 300, "stateFilter": {"include": ["ENABLED"]}}
        if next_token:
            body["nextToken"] = next_token
        result = campaigns_api.list_campaigns(body=json.dumps(body))
        payload = result.payload
        if isinstance(payload, dict):
            camps = payload.get('campaigns', [])
            next_token = payload.get('nextToken')
        else:
            camps = payload if payload else []
            next_token = None
        all_campaigns.extend(camps)
        if not next_token:
            break

    print(f"\n  ENABLED campaigns: {len(all_campaigns)}")

    # Classify campaigns by ASIN
    classified = {'star': [], 'question': [], 'cut': [], 'potential': [], 'skip': [], 'unmatched': []}
    for c in all_campaigns:
        quad = classify_campaign(c.get('name', ''), asin_map)
        classified[quad].append(c)

    for q in ['star', 'question', 'cut', 'potential', 'skip', 'unmatched']:
        if classified[q]:
            print(f"    {q:>10}: {len(classified[q])} campaigns")

    results = {
        'market': market_code,
        'star_budget_increases': [],
        'question_bid_reductions': [],
        'cut_bid_reductions': [],
        'errors': [],
    }

    # ── Step 2: STAR — no action (hard rule: never increase bids or budgets) ──
    star_camps = classified['star']
    if star_camps:
        print(f"\n  ⭐ STAR — No action ({len(star_camps)} campaigns)")
        print(f"    Hard rule: never increase bids or budgets. Maintain current settings.")

    # ── Step 3: QUESTION — reduce bids by 20% ──
    question_camps = classified['question']
    if question_camps:
        _reduce_bids(config, question_camps, 0.8, 'question', results, dry_run)

    # ── Step 4: CUT — reduce bids to minimum ──
    cut_camps = classified['cut']
    if cut_camps:
        _reduce_bids(config, cut_camps, 0.5, 'cut', results, dry_run)

    return results


def _reduce_bids(config, camps, multiplier, label, results, dry_run):
    """Reduce keyword and target bids for given campaigns."""
    action = f"{'⚠️ QUESTION' if label == 'question' else '🔴 CUT'}"
    pct = int((1 - multiplier) * 100)
    print(f"\n  {action} — Reducing bids by {pct}% ({len(camps)} campaigns)")

    camp_cids = {str(c.get('campaignId')) for c in camps}
    result_key = f'{label}_bid_reductions'

    # Get keywords
    kw_api = KeywordsV3(marketplace=config['marketplace'])
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

    # Get targets
    tgt_api = TargetsV3(marketplace=config['marketplace'])
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

    # Keyword bid reductions
    kw_updates = []
    for kw in q_kws:
        old_bid = float(kw.get('bid', 0))
        if old_bid <= 0:
            continue
        new_bid = round(max(old_bid * multiplier, BID_MIN), 2)
        if new_bid >= old_bid:
            continue
        kw_updates.append({"keywordId": str(kw.get('keywordId')), "bid": new_bid})
        results[result_key].append({
            'type': 'keyword', 'id': str(kw.get('keywordId')),
            'text': kw.get('keywordText', '')[:40],
            'old_bid': old_bid, 'new_bid': new_bid
        })

    # Target bid reductions
    tgt_updates = []
    for tgt in q_tgts:
        old_bid = float(tgt.get('bid', 0))
        if old_bid <= 0:
            continue
        new_bid = round(max(old_bid * multiplier, BID_MIN), 2)
        if new_bid >= old_bid:
            continue
        tgt_updates.append({"targetId": str(tgt.get('targetId')), "bid": new_bid})
        results[result_key].append({
            'type': 'target', 'id': str(tgt.get('targetId')),
            'text': str(tgt.get('expression', [{}])[0].get('value', 'auto') if tgt.get('expression') else 'auto')[:40],
            'old_bid': old_bid, 'new_bid': new_bid
        })

    print(f"    Bid changes: {len(kw_updates)} keywords, {len(tgt_updates)} targets")

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


# ══════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════
if __name__ == '__main__':
    dry_run = '--dry-run' in sys.argv
    single_market = None
    for arg in sys.argv[1:]:
        if arg.upper() in MARKET_CONFIG and arg != '--dry-run':
            single_market = arg.upper()

    if dry_run:
        print("🔍 DRY RUN MODE — no changes will be made\n")

    markets_to_run = [single_market] if single_market else list(MARKET_CONFIG.keys())
    all_results = []

    for mkt in markets_to_run:
        try:
            r = process_market(mkt, MARKET_CONFIG[mkt], dry_run=dry_run)
            all_results.append(r)
        except Exception as e:
            print(f"\n  ❌ {mkt} FAILED: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            all_results.append({'market': mkt, 'error': str(e)})

    # ── Summary ──
    print(f"\n\n{'='*70}")
    print(f"  SUMMARY — Flux Action Items Execution")
    print(f"  Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  Mode: {'DRY RUN' if dry_run else 'LIVE'}")
    print(f"{'='*70}")

    for r in all_results:
        mkt = r.get('market', '?')
        stars = len(r.get('star_budget_increases', []))
        q_bids = len(r.get('question_bid_reductions', []))
        c_bids = len(r.get('cut_bid_reductions', []))
        errs = len(r.get('errors', []))
        print(f"\n  {mkt}:")
        print(f"    ⭐ Star (no action): {stars} campaigns")
        print(f"    ⚠️  Bids -20%:       {q_bids} keywords/targets")
        print(f"    🔴 Bids -50% (cut):  {c_bids} keywords/targets")
        if errs:
            print(f"    ❌ Errors:           {errs}")

    # Save results to JSON
    output_path = Path(__file__).resolve().parent / 'flux_action_results.json'
    with open(output_path, 'w') as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\n  Results saved to: {output_path}")
    print(f"{'='*70}")
