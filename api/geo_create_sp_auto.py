"""
GEO — Create SP Auto campaign for S2503 120mm Fan (Potential quadrant)
Budget: $10/day  |  Default Bid: $0.21  |  Strategy: DOWN_ONLY

Parent: B0DJ2X2SK8 (S2503 120mm Fan)
Children with sales:
  B0B3XFZN7C  S2503 120mm Black 3-Pack   $299.40
  B0B3XDL218  S2503 120mm White 3-Pack   $149.70
  B0CHR7XPVX  S2503R 120mm Reverse 1pk   (under Cut parent, skip)

Usage:
  python3 api/geo_create_sp_auto.py --dry-run   # preview
  python3 api/geo_create_sp_auto.py              # create live
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

# ── Campaign Parameters ──
BID_CAP = 0.21          # GEO max bid
DAILY_BUDGET = 10.00    # $10/day
TODAY = datetime.now().strftime('%m%d%y')  # e.g. 031026

CAMPAIGN_NAME = f"US S2503-120mm B0DJ2X2SK8 SP Auto {TODAY}"
ADGROUP_NAME = f"S2503 120mm Fan Auto {TODAY}"

# ASINs to advertise (S2503 120mm family — parent + children with sales)
PRODUCT_ASINS = [
    "B0B3XFZN7C",  # S2503 120mm Black 3-Pack ($299.40 sales)
    "B0B3XDL218",  # S2503 120mm White 3-Pack ($149.70 sales)
]
# Note: B0CHR7XPVX is under the CUT parent (S2503R 120mm), not included here


def main():
    dry_run = '--dry-run' in sys.argv

    print(f"""
╔══════════════════════════════════════════════════════════╗
║  GEO — Create SP Auto Campaign: S2503 120mm Fan          ║
║  Profile: {GEO_PROFILE_ID}                      ║
║  Mode:    {'DRY RUN' if dry_run else 'LIVE':10s}                                     ║
╚══════════════════════════════════════════════════════════╝

  Campaign:   {CAMPAIGN_NAME}
  Type:       SP Auto (DOWN_ONLY)
  Budget:     ${DAILY_BUDGET:.2f}/day
  Bid Cap:    ${BID_CAP:.2f} (GEO max)
  Ad Group:   {ADGROUP_NAME}
  ASINs:      {', '.join(PRODUCT_ASINS)}
  Start Date: {datetime.now().strftime('%Y-%m-%d')}
""")

    if dry_run:
        print("🔍 DRY RUN — showing what would be created:\n")
        print("  Step 1: Create Campaign")
        print(f"    name: {CAMPAIGN_NAME}")
        print(f"    targetingType: AUTO")
        print(f"    budget: ${DAILY_BUDGET:.2f} DAILY")
        print(f"    dynamicBidding: DOWN_ONLY")
        print(f"    state: ENABLED")
        print()
        print("  Step 2: Create Ad Group")
        print(f"    name: {ADGROUP_NAME}")
        print(f"    defaultBid: ${BID_CAP:.2f}")
        print(f"    state: ENABLED")
        print()
        print("  Step 3: Create Product Ads")
        for asin in PRODUCT_ASINS:
            print(f"    ASIN: {asin}")
        print()
        print(f"  ⚠️  Bid cap verification:")
        print(f"    defaultBid = ${BID_CAP:.2f} = GEO max bid")
        print(f"    DOWN_ONLY strategy → bids can only go DOWN from ${BID_CAP:.2f}")
        print(f"    Amazon will never bid above ${BID_CAP:.2f}")
        print(f"    ✅ Within GEO range $0.16–$0.21")
        print()
        print("  Run without --dry-run to create.")
        return

    # ══════════════════════════════════════════
    # STEP 1: Create Campaign
    # ══════════════════════════════════════════
    print("Step 1: Creating campaign...")
    camps_api = CampaignsV3(marketplace=MARKETPLACE)

    campaign_body = [{
        "name": CAMPAIGN_NAME,
        "state": "ENABLED",
        "targetingType": "AUTO",
        "budget": {
            "budgetType": "DAILY",
            "budget": DAILY_BUDGET
        },
        "dynamicBidding": {
            "strategy": "LEGACY_FOR_SALES"  # DOWN_ONLY
        },
        "startDate": datetime.now().strftime('%Y-%m-%d')
    }]

    try:
        result = camps_api.create_campaigns(body=json.dumps({"campaigns": campaign_body}), prefer=True)
        payload = result.payload
        print(f"  Response: {json.dumps(payload, indent=2, default=str)[:500]}")

        # Extract campaign ID
        campaign_id = None
        if isinstance(payload, dict):
            success = payload.get('campaigns', {}).get('success', [])
            if success:
                campaign_id = str(success[0].get('campaignId', success[0].get('campaign', {}).get('campaignId', '')))
            errors = payload.get('campaigns', {}).get('error', [])
            if errors:
                print(f"  ❌ Errors: {json.dumps(errors, indent=2)}")
                return
        elif isinstance(payload, list) and payload:
            campaign_id = str(payload[0].get('campaignId', ''))

        if not campaign_id:
            print(f"  ❌ Could not extract campaignId from response")
            return

        print(f"  ✅ Campaign created: ID={campaign_id}")

    except AdvertisingApiException as e:
        print(f"  ❌ API Error: {e}")
        return
    except Exception as e:
        print(f"  ❌ Error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return

    # ══════════════════════════════════════════
    # STEP 2: Create Ad Group
    # ══════════════════════════════════════════
    print(f"\nStep 2: Creating ad group (defaultBid=${BID_CAP:.2f})...")
    ag_api = AdGroupsV3(marketplace=MARKETPLACE)

    adgroup_body = [{
        "name": ADGROUP_NAME,
        "campaignId": campaign_id,
        "defaultBid": BID_CAP,
        "state": "ENABLED"
    }]

    try:
        result = ag_api.create_ad_groups(body=json.dumps({"adGroups": adgroup_body}), prefer=True)
        payload = result.payload
        print(f"  Response: {json.dumps(payload, indent=2, default=str)[:500]}")

        adgroup_id = None
        if isinstance(payload, dict):
            success = payload.get('adGroups', {}).get('success', [])
            if success:
                adgroup_id = str(success[0].get('adGroupId', success[0].get('adGroup', {}).get('adGroupId', '')))
            errors = payload.get('adGroups', {}).get('error', [])
            if errors:
                print(f"  ❌ Errors: {json.dumps(errors, indent=2)}")
                return
        elif isinstance(payload, list) and payload:
            adgroup_id = str(payload[0].get('adGroupId', ''))

        if not adgroup_id:
            print(f"  ❌ Could not extract adGroupId from response")
            return

        print(f"  ✅ Ad Group created: ID={adgroup_id}")

    except AdvertisingApiException as e:
        print(f"  ❌ API Error: {e}")
        return
    except Exception as e:
        print(f"  ❌ Error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return

    # ══════════════════════════════════════════
    # STEP 3: Create Product Ads
    # ══════════════════════════════════════════
    print(f"\nStep 3: Creating {len(PRODUCT_ASINS)} product ads...")
    pa_api = ProductAdsV3(marketplace=MARKETPLACE)

    product_ads_body = []
    for asin in PRODUCT_ASINS:
        product_ads_body.append({
            "campaignId": campaign_id,
            "adGroupId": adgroup_id,
            "asin": asin,
            "state": "ENABLED"
        })

    try:
        result = pa_api.create_product_ads(body=json.dumps({"productAds": product_ads_body}), prefer=True)
        payload = result.payload
        print(f"  Response: {json.dumps(payload, indent=2, default=str)[:500]}")

        if isinstance(payload, dict):
            success = payload.get('productAds', {}).get('success', [])
            errors = payload.get('productAds', {}).get('error', [])
            print(f"  ✅ Product Ads created: {len(success)} success")
            if errors:
                print(f"  ⚠️  Errors: {len(errors)}")
                for e in errors[:3]:
                    print(f"    {json.dumps(e)}")

    except AdvertisingApiException as e:
        print(f"  ❌ API Error: {e}")
        return
    except Exception as e:
        print(f"  ❌ Error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return

    # ── Summary ──
    print(f"""
{'='*60}
  ✅ SP Auto Campaign Created Successfully!
{'='*60}
  Campaign:  {CAMPAIGN_NAME}
  ID:        {campaign_id}
  Budget:    ${DAILY_BUDGET:.2f}/day
  Bid Cap:   ${BID_CAP:.2f} (DOWN_ONLY)
  Ad Group:  {adgroup_id}
  ASINs:     {', '.join(PRODUCT_ASINS)}
{'='*60}
""")


if __name__ == '__main__':
    main()
