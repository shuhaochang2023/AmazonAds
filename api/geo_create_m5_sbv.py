"""
GEO — Create Sponsored Brands Video (SBV) campaigns for M5 Case
Uses existing video assets already in Amazon's Creative Asset Library
(generated via Amazon Video Builder)

M5 Case video assets:
  B0DGFX3T34 (Black/Grey): 3 MULTI_SCENE + 1 SUMMARIZED + 1 ANIMATED = 5 videos
  B0DGFS7QTL (Black/Green): 2 MULTI_SCENE + 1 SUMMARIZED = 3 videos

Budget: $1/day  |  Bid: $0.21  |  State: PAUSED (default)

Usage:
  python3 api/geo_create_m5_sbv.py --dry-run   # preview
  python3 api/geo_create_m5_sbv.py              # create live (PAUSED)
  python3 api/geo_create_m5_sbv.py --enable     # create live (ENABLED)
"""

import os
import sys
import json
import time
import requests
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

from ad_api.api.sb import CampaignsV4, AdGroupsV4, AdsV4
from ad_api.base import Marketplaces, AdvertisingApiException

MARKETPLACE = Marketplaces.US

# ── Parameters ──
BID = 0.21
DAILY_BUDGET = 1.00
TODAY = datetime.now().strftime('%m%d%y')

# M5 Case child ASINs (all color variants)
M5_ASINS = ["B0DGFX3T34", "B0DGFS7QTL", "B0DGFW4N61", "B0DGFW5G2G"]

# ── Existing video assets from Amazon Creative Asset Library ──
# These were generated via Amazon Video Builder and are already uploaded
SBV_CAMPAIGNS = [
    # B0DGFX3T34 (Black/Grey) videos
    {
        "asset_id": "amzn1.assetlibrary.asset1.10b2302fee422e76c40323f9be2c4969",
        "campaign_name": f"GEO SBV M5-BG Summary {TODAY}",
        "ad_name": f"M5 Case Black-Grey Summary {TODAY}",
        "asin": "B0DGFX3T34",
        "description": "M5 Case Black/Grey — Summarized Video",
    },
    {
        "asset_id": "amzn1.assetlibrary.asset1.ccd315c34e19e85473d928c14b9f9ff5",
        "campaign_name": f"GEO SBV M5-BG MultiScene1 {TODAY}",
        "ad_name": f"M5 Case Black-Grey MultiScene1 {TODAY}",
        "asin": "B0DGFX3T34",
        "description": "M5 Case Black/Grey — Multi-Scene #1",
    },
    {
        "asset_id": "amzn1.assetlibrary.asset1.5eb5e4e85bb6d127ee1ccce288d48ef5",
        "campaign_name": f"GEO SBV M5-BG MultiScene2 {TODAY}",
        "ad_name": f"M5 Case Black-Grey MultiScene2 {TODAY}",
        "asin": "B0DGFX3T34",
        "description": "M5 Case Black/Grey — Multi-Scene #2",
    },
    {
        "asset_id": "amzn1.assetlibrary.asset1.d901db0e0bab69ecc2e776fb5f0e097c",
        "campaign_name": f"GEO SBV M5-BG MultiScene3 {TODAY}",
        "ad_name": f"M5 Case Black-Grey MultiScene3 {TODAY}",
        "asin": "B0DGFX3T34",
        "description": "M5 Case Black/Grey — Multi-Scene #3",
    },
    {
        "asset_id": "amzn1.assetlibrary.asset1.3054e8630a2a20d22c7c8a79d3c4eb68",
        "campaign_name": f"GEO SBV M5-BG Animated {TODAY}",
        "ad_name": f"M5 Case Black-Grey Animated {TODAY}",
        "asin": "B0DGFX3T34",
        "description": "M5 Case Black/Grey — Animated Image",
    },
    # B0DGFS7QTL (Black/Green) videos
    {
        "asset_id": "amzn1.assetlibrary.asset1.2c1689d2429705b04812fc069724de19",
        "campaign_name": f"GEO SBV M5-BN Summary {TODAY}",
        "ad_name": f"M5 Case Black-Green Summary {TODAY}",
        "asin": "B0DGFS7QTL",
        "description": "M5 Case Black/Green — Summarized Video",
    },
    {
        "asset_id": "amzn1.assetlibrary.asset1.c88dafaa98c25c3f1f5ee35e03054d21",
        "campaign_name": f"GEO SBV M5-BN MultiScene1 {TODAY}",
        "ad_name": f"M5 Case Black-Green MultiScene1 {TODAY}",
        "asin": "B0DGFS7QTL",
        "description": "M5 Case Black/Green — Multi-Scene #1",
    },
    {
        "asset_id": "amzn1.assetlibrary.asset1.a8aed75b78fd1cb1eb203f50aa7bf9ed",
        "campaign_name": f"GEO SBV M5-BN MultiScene2 {TODAY}",
        "ad_name": f"M5 Case Black-Green MultiScene2 {TODAY}",
        "asin": "B0DGFS7QTL",
        "description": "M5 Case Black/Green — Multi-Scene #2",
    },
]


def get_auth_headers():
    """Get authenticated headers from a working SB API instance."""
    camp_api = CampaignsV4(marketplace=MARKETPLACE)
    return dict(camp_api.headers)


def create_sb_campaign(headers, name, state, budget):
    """Create an SB campaign via direct HTTP (v4 API)."""
    url = "https://advertising-api.amazon.com/sb/v4/campaigns"
    json_version = "application/vnd.sbcampaignresource.v4+json"
    req_headers = {**headers, "Accept": json_version}

    body = {
        "campaigns": [{
            "name": name,
            "state": state,
            "budget": budget,
            "budgetType": "DAILY",
            "bidOptimization": True,
            "brandEntityId": "ENTITY6K5TG6VHVS15",
        }]
    }
    resp = requests.post(url, headers=req_headers, json=body)
    data = resp.json()
    print(f"    Campaign response: {json.dumps(data, indent=2)[:500]}")

    success = data.get('campaigns', {}).get('success', [])
    errors = data.get('campaigns', {}).get('error', [])
    if errors:
        print(f"    Campaign errors: {json.dumps(errors, indent=2)}")
        return None
    if success:
        return str(success[0].get('campaignId', success[0].get('campaign', {}).get('campaignId', '')))
    return None


def create_sb_adgroup(headers, campaign_id, name):
    """Create an SB ad group via direct HTTP (v4 API)."""
    url = "https://advertising-api.amazon.com/sb/v4/adGroups"
    json_version = "application/vnd.sbadgroupresource.v4+json"
    req_headers = {**headers, "Accept": json_version}

    body = {
        "adGroups": [{
            "campaignId": campaign_id,
            "name": name,
            "state": "ENABLED",
        }]
    }
    resp = requests.post(url, headers=req_headers, json=body)
    data = resp.json()
    print(f"    AdGroup response: {json.dumps(data, indent=2)[:500]}")

    success = data.get('adGroups', {}).get('success', [])
    errors = data.get('adGroups', {}).get('error', [])
    if errors:
        print(f"    AdGroup errors: {json.dumps(errors, indent=2)}")
        return None
    if success:
        return str(success[0].get('adGroupId', success[0].get('adGroup', {}).get('adGroupId', '')))
    return None


def create_video_ad(headers, adgroup_id, ad_name, asset_id, asin, state):
    """Create an SB video ad via direct HTTP (v4 API)."""
    url = "https://advertising-api.amazon.com/sb/v4/ads/video"
    json_version = "application/vnd.sbadresource.v4+json"
    req_headers = {**headers, "Accept": json_version}

    body = {
        "ads": [{
            "name": ad_name,
            "state": state,
            "adGroupId": adgroup_id,
            "creative": {
                "asins": [asin],
                "videoAssetIds": [asset_id],
            }
        }]
    }
    resp = requests.post(url, headers=req_headers, json=body)
    data = resp.json()
    print(f"    Ad response: {json.dumps(data, indent=2)[:500]}")

    success = data.get('ads', {}).get('success', [])
    errors = data.get('ads', {}).get('error', [])
    if errors:
        print(f"    Ad errors: {json.dumps(errors, indent=2)}")
        return None
    if success:
        return str(success[0].get('adId', success[0].get('ad', {}).get('adId', '')))
    return None


def main():
    dry_run = '--dry-run' in sys.argv
    enable = '--enable' in sys.argv
    state = 'ENABLED' if enable else 'PAUSED'

    print(f"""
{'='*65}
  GEO — Create M5 Case SBV Campaigns (from Asset Library)
  Profile: {GEO_PROFILE_ID}
  Mode:    {'DRY RUN' if dry_run else f'LIVE ({state})'}
  Budget:  ${DAILY_BUDGET:.2f}/day  |  Bid: ${BID:.2f}
  Product: M5 Case (parent B0DF7QSTG3)
  Videos:  {len(SBV_CAMPAIGNS)} (from Amazon Video Builder)
{'='*65}
""")

    for i, camp in enumerate(SBV_CAMPAIGNS, 1):
        print(f"  {i}. {camp['campaign_name']}")
        print(f"     ASIN: {camp['asin']} | AssetID: ...{camp['asset_id'][-12:]}")
        print(f"     {camp['description']}")
        print()

    if dry_run:
        print("  DRY RUN — no changes made.")
        print("  Run without --dry-run to create campaigns.")
        print("  Add --enable to create as ENABLED (default: PAUSED).")
        return

    # Get auth headers from working API
    headers = get_auth_headers()
    results = []

    for i, camp in enumerate(SBV_CAMPAIGNS, 1):
        print(f"\n{'='*65}")
        print(f"  Campaign {i}/{len(SBV_CAMPAIGNS)}: {camp['campaign_name']}")
        print(f"{'='*65}")

        # Step 1: Create campaign
        print(f"  Step 1: Create SB campaign ({state})...")
        try:
            campaign_id = create_sb_campaign(headers, camp['campaign_name'], state, DAILY_BUDGET)
        except Exception as e:
            print(f"  Error: {e}")
            continue
        if not campaign_id:
            print(f"  Failed to create campaign")
            continue
        print(f"  Campaign created: {campaign_id}")

        # Step 2: Create ad group
        print(f"\n  Step 2: Create ad group...")
        ag_name = f"M5 SBV {camp['asin'][-4:]} {i} {TODAY}"
        try:
            adgroup_id = create_sb_adgroup(headers, campaign_id, ag_name)
        except Exception as e:
            print(f"  Error: {e}")
            continue
        if not adgroup_id:
            print(f"  Failed to create ad group")
            continue
        print(f"  Ad group created: {adgroup_id}")

        # Step 3: Create video ad with existing asset
        print(f"\n  Step 3: Create video ad (assetId=...{camp['asset_id'][-12:]})...")
        try:
            ad_id = create_video_ad(headers, adgroup_id, camp['ad_name'], camp['asset_id'], camp['asin'], state)
        except Exception as e:
            print(f"  Error: {e}")
            continue
        if not ad_id:
            print(f"  Failed to create video ad")
            continue
        print(f"  Video ad created: {ad_id}")

        results.append({
            'name': camp['campaign_name'],
            'asin': camp['asin'],
            'campaign_id': campaign_id,
            'adgroup_id': adgroup_id,
            'ad_id': ad_id,
            'asset_id': camp['asset_id'],
        })

        # Brief pause between campaigns
        if i < len(SBV_CAMPAIGNS):
            time.sleep(1)

    # ── Summary ──
    print(f"""
{'='*65}
  M5 Case SBV Campaign Creation Summary
{'='*65}""")

    for r in results:
        print(f"  {r['name']}")
        print(f"    Campaign: {r['campaign_id']} | AdGroup: {r['adgroup_id']} | Ad: {r['ad_id']}")
        print(f"    ASIN: {r['asin']} | AssetId: ...{r['asset_id'][-12:]}")
    print(f"""
  Total: {len(results)}/{len(SBV_CAMPAIGNS)} campaigns created
  Budget: ${DAILY_BUDGET:.2f}/day each | ${DAILY_BUDGET * len(results):.2f}/day total
  State: {state}
{'='*65}
""")

    if state == 'PAUSED':
        print("  Campaigns created as PAUSED. To enable:")
        print("    python3 api/geo_create_m5_sbv.py --enable")

    # Save results
    results_file = ROOT / 'api' / 'geo_m5_sbv_results.json'
    with open(results_file, 'w') as f:
        json.dump({
            'timestamp': datetime.now().isoformat(),
            'profile_id': GEO_PROFILE_ID,
            'product': 'M5 Case (B0DF7QSTG3)',
            'budget': DAILY_BUDGET,
            'bid': BID,
            'state': state,
            'campaigns': results,
        }, f, indent=2)
    print(f"  Results saved to: {results_file}")


if __name__ == '__main__':
    main()
