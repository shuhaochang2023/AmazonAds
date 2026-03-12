"""
DAIKEN US — Kids Fish Oil Budget Boost
⚠️ DEPRECATED — This script increases budgets, which violates the hard rule:
   "永遠不提高 bid 或 budget。只能降低或暫停。"
   DO NOT RUN this script. Kept for reference only.

Original purpose:
1. Pull all SP campaigns via API
2. Filter Kids Fish Oil campaigns
3. Running campaigns with budget > $1: increase budget 50%
4. $1 campaigns: restore to $3
5. Bid ceiling: $5 (no bid changes in this script — budget only)
"""

import os
import sys
import json
import requests
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / '.env'
PROFILE_ID = '1243647931853395'  # DAIKEN US


def load_env():
    env = {}
    with open(ENV_PATH) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                env[k.strip()] = v.strip()
    return env


def get_access_token(env):
    resp = requests.post('https://api.amazon.com/auth/o2/token', data={
        'grant_type': 'refresh_token',
        'client_id': env['AMAZON_ADS_CLIENT_ID'],
        'client_secret': env['AMAZON_ADS_CLIENT_SECRET'],
        'refresh_token': env['AMAZON_ADS_REFRESH_TOKEN'],
    })
    resp.raise_for_status()
    return resp.json()['access_token']


def fetch_all_sp_campaigns(access_token, client_id):
    CT = 'application/vnd.spcampaign.v3+json'
    headers = {
        'Amazon-Advertising-API-ClientId': client_id,
        'Amazon-Advertising-API-Scope': PROFILE_ID,
        'Authorization': f'Bearer {access_token}',
        'Content-Type': CT,
        'Accept': CT,
    }
    all_camps = []
    next_token = None
    for _ in range(50):
        body = {'maxResults': 100}
        if next_token:
            body['nextToken'] = next_token
        resp = requests.post(
            'https://advertising-api.amazon.com/sp/campaigns/list',
            headers=headers, json=body
        )
        if resp.status_code != 200:
            print(f'Error fetching campaigns: {resp.status_code} {resp.text[:300]}')
            break
        data = resp.json()
        all_camps.extend(data.get('campaigns', []))
        next_token = data.get('nextToken')
        if not next_token:
            break
    return all_camps


def is_kids_fish_oil(name):
    nl = name.lower()
    # Exclude non-fish-oil products
    if 'fish oil omega' in nl or nl.startswith('fish oil omega'):
        return False
    if 'premium' in nl and 'fish' in nl:
        return False
    if any(x in nl for x in ['natto', 'multi-enzyme', 'maca', 'bitter melon',
                              'bitter gourd', 'lutein', 'vitamin', 'l-arginine']):
        return False
    return any(x in nl for x in ['fish', 'kids fish', 'omega', 'gummy', 'cod liver', 'cod-liver'])


def update_campaign_budget(access_token, client_id, campaign_id, new_budget):
    CT = 'application/vnd.spcampaign.v3+json'
    headers = {
        'Amazon-Advertising-API-ClientId': client_id,
        'Amazon-Advertising-API-Scope': PROFILE_ID,
        'Authorization': f'Bearer {access_token}',
        'Content-Type': CT,
        'Accept': CT,
    }
    body = {
        'campaigns': [{
            'campaignId': campaign_id,
            'budget': {
                'budget': new_budget,
                'budgetType': 'DAILY',
            }
        }]
    }
    resp = requests.put(
        'https://advertising-api.amazon.com/sp/campaigns',
        headers=headers, json=body
    )
    return resp.status_code, resp.json()


def enable_campaign(access_token, client_id, campaign_id, new_budget=None):
    CT = 'application/vnd.spcampaign.v3+json'
    headers = {
        'Amazon-Advertising-API-ClientId': client_id,
        'Amazon-Advertising-API-Scope': PROFILE_ID,
        'Authorization': f'Bearer {access_token}',
        'Content-Type': CT,
        'Accept': CT,
    }
    update = {
        'campaignId': campaign_id,
        'state': 'ENABLED',
    }
    if new_budget:
        update['budget'] = {'budget': new_budget, 'budgetType': 'DAILY'}
    body = {'campaigns': [update]}
    resp = requests.put(
        'https://advertising-api.amazon.com/sp/campaigns',
        headers=headers, json=body
    )
    return resp.status_code, resp.json()


def main():
    print("⛔ BLOCKED: This script increases budgets, which violates the hard rule.")
    print("   Hard rule: 永遠不提高 bid 或 budget。只能降低或暫停。")
    print("   Script disabled. Exiting.")
    return

def _main_disabled():
    dry_run = '--dry-run' in sys.argv
    ts = datetime.now().strftime('%Y-%m-%d %H:%M')
    print(f'[{ts}] DAIKEN Kids Fish Oil Budget Boost {"(DRY RUN)" if dry_run else ""}')
    print('=' * 70)

    env = load_env()
    access_token = get_access_token(env)
    client_id = env['AMAZON_ADS_CLIENT_ID']

    print('Fetching all SP campaigns...')
    all_camps = fetch_all_sp_campaigns(access_token, client_id)
    print(f'Total SP campaigns: {len(all_camps)}')

    # Filter Kids Fish Oil
    fish_oil = []
    for c in all_camps:
        name = c.get('name', '')
        if is_kids_fish_oil(name):
            budget_obj = c.get('budget', {})
            budget = float(budget_obj.get('budget', 0)) if isinstance(budget_obj, dict) else 0
            state = c.get('state', '').upper()
            fish_oil.append({
                'id': c.get('campaignId'),
                'name': name,
                'state': state,
                'budget': budget,
            })

    fish_oil.sort(key=lambda x: x['budget'], reverse=True)

    enabled = [c for c in fish_oil if c['state'] == 'ENABLED']
    paused = [c for c in fish_oil if c['state'] == 'PAUSED']

    print(f'\nKids Fish Oil campaigns: {len(fish_oil)}')
    print(f'  ENABLED: {len(enabled)} (total daily budget: ${sum(c["budget"] for c in enabled):,.2f})')
    print(f'  PAUSED:  {len(paused)}')

    # --- Plan ---
    actions = []

    # 1. Enabled campaigns with budget > $1: increase 50%
    for c in enabled:
        if c['budget'] > 1:
            new_b = round(c['budget'] * 1.5, 2)
            actions.append({**c, 'action': 'BOOST_50', 'new_budget': new_b})
        else:
            # 2. $1 campaigns: restore to $3
            actions.append({**c, 'action': 'RESTORE_3', 'new_budget': 3.0})

    # 3. Paused campaigns: enable with $3 budget
    for c in paused:
        actions.append({**c, 'action': 'ENABLE', 'new_budget': max(c['budget'], 3.0)})

    total_old = sum(a['budget'] for a in actions)
    total_new = sum(a['new_budget'] for a in actions)

    print(f'\n{"Action":<12} {"State":<8} {"Old $":<10} {"New $":<10} Campaign')
    print('-' * 100)
    for a in actions:
        print(f'{a["action"]:<12} {a["state"]:<8} ${a["budget"]:<9.2f} ${a["new_budget"]:<9.2f} {a["name"][:60]}')

    print('-' * 100)
    print(f'Total daily budget: ${total_old:,.2f} → ${total_new:,.2f} (+${total_new - total_old:,.2f})')
    print(f'Campaigns to update: {len(actions)} ({len([a for a in actions if a["action"] == "ENABLE"])} to enable)')

    if dry_run:
        print('\n--- DRY RUN — no changes made ---')
        return

    # Execute
    print(f'\nExecuting {len(actions)} updates...')
    success = 0
    errors = 0
    for a in actions:
        if a['action'] == 'ENABLE':
            code, resp = enable_campaign(access_token, client_id, a['id'], a['new_budget'])
        else:
            code, resp = update_campaign_budget(access_token, client_id, a['id'], a['new_budget'])

        if code == 200:
            success += 1
        else:
            errors += 1
            print(f'  ERROR [{code}] {a["name"][:50]}: {json.dumps(resp)[:200]}')

    print(f'\nDone: {success} success, {errors} errors')

    # Save log
    log = {
        'timestamp': ts,
        'total_campaigns': len(actions),
        'enabled_boosted': len([a for a in actions if a['action'] == 'BOOST_50']),
        'enabled_restored': len([a for a in actions if a['action'] == 'RESTORE_3']),
        'paused_enabled': len([a for a in actions if a['action'] == 'ENABLE']),
        'old_total_daily': round(total_old, 2),
        'new_total_daily': round(total_new, 2),
        'success': success,
        'errors': errors,
        'actions': actions,
    }
    log_path = ROOT / 'api' / 'boost_kids_fishoil_log.json'
    log_path.write_text(json.dumps(log, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'Log saved: {log_path}')


if __name__ == '__main__':
    main()
