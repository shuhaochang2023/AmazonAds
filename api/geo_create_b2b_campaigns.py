"""
GEO — Create SP Auto campaigns targeting Amazon Business (B2B) buyers
siteRestrictions: ["AMAZON_BUSINESS"] — ads appear exclusively on Amazon Business

Products:
  1. M5 Case (flagship, $41,312 sales) — B0DGFX3T34, B0DGFS7QTL, B0DGFW4N61, B0DGFW5G2G
  2. Eskimo Pro 360/420 AIO (TACOS 2.9%) — B0DHX99JLW, B0DHXCYKR6, B0DHXG3QPM
  3. S2503 Fan 3pk (bulk appeal) — B0B3XFZN7C, B0B3XDL218, B0DGGVRBX2

Budget: $5/day per campaign  |  Bid: $0.21 (GEO max)  |  Strategy: DOWN_ONLY

Usage:
  python3 api/geo_create_b2b_campaigns.py --dry-run   # preview
  python3 api/geo_create_b2b_campaigns.py              # create live (PAUSED)
  python3 api/geo_create_b2b_campaigns.py --enable     # create live (ENABLED)
"""

import os
import json
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
            if key == 'AMAZON_ADS_CLIENT_ID': os.environ['AD_API_CLIENT_ID'] = val
            elif key == 'AMAZON_ADS_CLIENT_SECRET': os.environ['AD_API_CLIENT_SECRET'] = val
            elif key == 'AMAZON_ADS_REFRESH_TOKEN': os.environ['AD_API_REFRESH_TOKEN'] = val

GEO_PROFILE_ID = '3947387233604911'
os.environ['AD_API_PROFILE_ID'] = GEO_PROFILE_ID

from ad_api.api.sp import CampaignsV3, AdGroupsV3, ProductAdsV3
from ad_api.base import Marketplaces, AdvertisingApiException

MARKETPLACE = Marketplaces.US

# ── Parameters ──
BID_CAP = 0.21
DAILY_BUDGET = 5.00
TODAY = datetime.now().strftime('%m%d%y')

# ── B2B Campaign Definitions ──
B2B_CAMPAIGNS = [
    {
        "campaign_name": f"GEO B2B M5F-Case SP Auto {TODAY}",
        "adgroup_name": f"M5F Case B2B Auto {TODAY}",
        "products": [
            {"asin": "B0DGFX3T34", "sku": "GEO-M5F-BG"},   # M5F Case Black/Grey +Fans
            {"asin": "B0DGFS7QTL", "sku": "GEO-M5F-BNV"},  # M5F Case Black/Green +Fans
            {"asin": "B0DGFW4N61", "sku": "GEO-M5F-BY"},   # M5F Case Black/Yellow +Fans
            {"asin": "B0DGFW5G2G", "sku": "GEO-M5F-W"},    # M5F Case White +Fans
        ],
        "description": "M5 Case — flagship product, workstation appeal for B2B buyers"
    },
    {
        "campaign_name": f"GEO B2B Eskimo-Pro SP Auto {TODAY}",
        "adgroup_name": f"Eskimo Pro AIO B2B Auto {TODAY}",
        "products": [
            {"asin": "B0DHX99JLW", "sku": "GEO-EP-36B"},   # Eskimo Pro 360 Black
            {"asin": "B0DHXCYKR6", "sku": "GEO-EP-42B"},   # Eskimo Pro 420 Black
            {"asin": "B0DHXG3QPM", "sku": "GEO-EP-42W"},   # Eskimo Pro 420 White
        ],
        "description": "Eskimo Pro AIO — professional-grade cooling for IT/enterprise builds"
    },
    {
        "campaign_name": f"GEO B2B S2503-Fan-3pk SP Auto {TODAY}",
        "adgroup_name": f"S2503 Fan 3pk B2B Auto {TODAY}",
        "products": [
            {"asin": "B0B3XFZN7C", "sku": "GEO-S2503B-3"},   # S2503 120mm Black 3-Pack
            {"asin": "B0B3XDL218", "sku": "GEO-S2503W-3"},    # S2503 120mm White 3-Pack
            {"asin": "B0DGGVRBX2", "sku": "GEO-S2503B-14T"},  # S2503 140mm Black 3-Pack
        ],
        "description": "S2503 Fan 3-Packs — bulk quantity appeal for B2B / IT departments"
    },
]


def create_campaign(camps_api, name, state):
    body = [{
        "name": name,
        "state": state,
        "targetingType": "AUTO",
        "budget": {"budgetType": "DAILY", "budget": DAILY_BUDGET},
        "dynamicBidding": {"strategy": "LEGACY_FOR_SALES"},
        "startDate": datetime.now().strftime('%Y-%m-%d'),
        "siteRestrictions": ["AMAZON_BUSINESS"]
    }]
    result = camps_api.create_campaigns(body=json.dumps({"campaigns": body}), prefer=True)
    payload = result.payload
    success = payload.get('campaigns', {}).get('success', [])
    errors = payload.get('campaigns', {}).get('error', [])
    if errors:
        print(f"  ❌ Errors: {json.dumps(errors, indent=2)}")
        return None
    if success:
        cid = str(success[0].get('campaignId', success[0].get('campaign', {}).get('campaignId', '')))
        return cid
    return None


def create_adgroup(ag_api, campaign_id, name):
    body = [{
        "name": name,
        "campaignId": campaign_id,
        "defaultBid": BID_CAP,
        "state": "ENABLED"
    }]
    result = ag_api.create_ad_groups(body=json.dumps({"adGroups": body}), prefer=True)
    payload = result.payload
    success = payload.get('adGroups', {}).get('success', [])
    errors = payload.get('adGroups', {}).get('error', [])
    if errors:
        print(f"  ❌ Errors: {json.dumps(errors, indent=2)}")
        return None
    if success:
        agid = str(success[0].get('adGroupId', success[0].get('adGroup', {}).get('adGroupId', '')))
        return agid
    return None


def create_product_ads(pa_api, campaign_id, adgroup_id, products):
    body = [{"campaignId": campaign_id, "adGroupId": adgroup_id, "asin": p["asin"], "sku": p["sku"], "state": "ENABLED"} for p in products]
    result = pa_api.create_product_ads(body=json.dumps({"productAds": body}), prefer=True)
    payload = result.payload
    success = payload.get('productAds', {}).get('success', [])
    errors = payload.get('productAds', {}).get('error', [])
    if errors:
        print(f"  ⚠️  Ad errors: {json.dumps(errors[:3], indent=2)}")
    return len(success)


def main():
    dry_run = '--dry-run' in sys.argv
    enable = '--enable' in sys.argv
    state = 'ENABLED' if enable else 'PAUSED'

    print(f"""
╔══════════════════════════════════════════════════════════════╗
║  GEO — Create B2B SP Auto Campaigns (Amazon Business Only)  ║
║  Profile: {GEO_PROFILE_ID}                          ║
║  Mode:    {'DRY RUN' if dry_run else f'LIVE ({state})':12s}                                    ║
║  siteRestrictions: ["AMAZON_BUSINESS"]                       ║
╚══════════════════════════════════════════════════════════════╝
""")

    for i, camp in enumerate(B2B_CAMPAIGNS, 1):
        print(f"  Campaign {i}: {camp['campaign_name']}")
        print(f"    {camp['description']}")
        print(f"    ASINs: {', '.join(p['asin'] for p in camp['products'])}")
        print(f"    Budget: ${DAILY_BUDGET:.2f}/day · Bid: ${BID_CAP:.2f} · DOWN_ONLY")
        print()

    if dry_run:
        print("  🔍 DRY RUN — no changes made. Run without --dry-run to create.")
        print("     Add --enable to create as ENABLED (default: PAUSED).")
        return

    camps_api = CampaignsV3(marketplace=MARKETPLACE)
    ag_api = AdGroupsV3(marketplace=MARKETPLACE)
    pa_api = ProductAdsV3(marketplace=MARKETPLACE)

    results = []

    for i, camp in enumerate(B2B_CAMPAIGNS, 1):
        print(f"{'='*60}")
        print(f"  Campaign {i}/3: {camp['campaign_name']}")
        print(f"{'='*60}")

        # Step 1: Create Campaign
        print(f"  Step 1: Creating B2B campaign ({state})...")
        try:
            campaign_id = create_campaign(camps_api, camp['campaign_name'], state)
        except AdvertisingApiException as e:
            print(f"  ❌ API Error: {e}")
            continue
        if not campaign_id:
            print(f"  ❌ Failed to create campaign")
            continue
        print(f"  ✅ Campaign: {campaign_id}")

        # Step 2: Create Ad Group
        print(f"  Step 2: Creating ad group (bid=${BID_CAP:.2f})...")
        try:
            adgroup_id = create_adgroup(ag_api, campaign_id, camp['adgroup_name'])
        except AdvertisingApiException as e:
            print(f"  ❌ API Error: {e}")
            continue
        if not adgroup_id:
            print(f"  ❌ Failed to create ad group")
            continue
        print(f"  ✅ Ad Group: {adgroup_id}")

        # Step 3: Create Product Ads
        print(f"  Step 3: Creating {len(camp['products'])} product ads...")
        try:
            count = create_product_ads(pa_api, campaign_id, adgroup_id, camp['products'])
        except AdvertisingApiException as e:
            print(f"  ❌ API Error: {e}")
            continue
        print(f"  ✅ Product Ads: {count} created")

        results.append({
            'name': camp['campaign_name'],
            'campaign_id': campaign_id,
            'adgroup_id': adgroup_id,
            'ads': count,
            'asins': [p['asin'] for p in camp['products']]
        })
        print()

    # Summary
    print(f"""
{'='*60}
  B2B Campaign Creation Summary
{'='*60}""")
    for r in results:
        print(f"  ✅ {r['name']}")
        print(f"     Campaign: {r['campaign_id']} · AdGroup: {r['adgroup_id']}")
        print(f"     {r['ads']} ads · ASINs: {', '.join(r['asins'])}")
    print(f"""
  Total: {len(results)} campaigns · ${DAILY_BUDGET:.2f}/day each · ${DAILY_BUDGET * len(results):.2f}/day total
  Site: Amazon Business only (B2B)
  State: {state}
{'='*60}
""")
    if state == 'PAUSED':
        print("  Campaigns created as PAUSED. To enable:")
        print("    python3 api/geo_create_b2b_campaigns.py --enable")
        print("  Or enable manually in Amazon Ads Console.")


if __name__ == '__main__':
    main()
