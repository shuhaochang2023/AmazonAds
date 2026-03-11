"""
DAIKEN US — Budget Guard (Auto-Pause / Auto-Resume)

Logic:
- When MTD pacing >= 90% of target → PAUSE all enabled campaigns
- Daily at 15:00 Taiwan time → RESUME all paused-by-guard campaigns
- Tracks which campaigns were paused by this script (not manually paused)

Runs via cron every 3 hours + at 15:00 TW daily.
"""

import os
import json
import requests
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / '.env'
GUARD_STATE = ROOT / 'api' / 'budget_guard_state.json'
PACING_JSON = ROOT / 'api' / 'budget_pacing.json'

PROFILE_ID = '1243647931853395'  # DAIKEN US
PAUSE_THRESHOLD = 95  # pause at 95% daily pacing
RESUME_HOUR_TW = 15   # resume at 15:00 Taiwan time (UTC+8)


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


def load_guard_state():
    if GUARD_STATE.exists():
        return json.loads(GUARD_STATE.read_text())
    return {'paused_campaigns': [], 'last_action': None, 'last_action_time': None}


def save_guard_state(state):
    GUARD_STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False))


def fetch_sp_campaigns(access_token, client_id):
    CT = 'application/vnd.spcampaign.v3+json'
    headers = {
        'Amazon-Advertising-API-ClientId': client_id,
        'Amazon-Advertising-API-Scope': PROFILE_ID,
        'Authorization': f'Bearer {access_token}',
        'Content-Type': CT, 'Accept': CT,
    }
    all_camps = []
    next_token = None
    for _ in range(50):
        body = {'maxResults': 100, 'stateFilter': {'include': ['ENABLED']}}
        if next_token:
            body['nextToken'] = next_token
        resp = requests.post(
            'https://advertising-api.amazon.com/sp/campaigns/list',
            headers=headers, json=body
        )
        if resp.status_code != 200:
            break
        data = resp.json()
        all_camps.extend(data.get('campaigns', []))
        next_token = data.get('nextToken')
        if not next_token:
            break
    return all_camps


def pause_campaigns(access_token, client_id, campaign_ids):
    """Pause a list of SP campaigns."""
    CT = 'application/vnd.spcampaign.v3+json'
    headers = {
        'Amazon-Advertising-API-ClientId': client_id,
        'Amazon-Advertising-API-Scope': PROFILE_ID,
        'Authorization': f'Bearer {access_token}',
        'Content-Type': CT, 'Accept': CT,
    }
    # API accepts batch updates
    updates = [{'campaignId': cid, 'state': 'PAUSED'} for cid in campaign_ids]
    # Process in batches of 10
    paused = 0
    for i in range(0, len(updates), 10):
        batch = updates[i:i+10]
        body = {'campaigns': batch}
        resp = requests.put(
            'https://advertising-api.amazon.com/sp/campaigns',
            headers=headers, json=body
        )
        if resp.status_code == 207:
            results = resp.json().get('campaigns', {})
            paused += len([r for r in results.get('success', []) if r])
        elif resp.status_code == 200:
            paused += len(batch)
        else:
            print(f'  Pause batch error: {resp.status_code} {resp.text[:200]}')
    return paused


def resume_campaigns(access_token, client_id, campaign_ids):
    """Resume (enable) a list of SP campaigns."""
    CT = 'application/vnd.spcampaign.v3+json'
    headers = {
        'Amazon-Advertising-API-ClientId': client_id,
        'Amazon-Advertising-API-Scope': PROFILE_ID,
        'Authorization': f'Bearer {access_token}',
        'Content-Type': CT, 'Accept': CT,
    }
    updates = [{'campaignId': cid, 'state': 'ENABLED'} for cid in campaign_ids]
    resumed = 0
    for i in range(0, len(updates), 10):
        batch = updates[i:i+10]
        body = {'campaigns': batch}
        resp = requests.put(
            'https://advertising-api.amazon.com/sp/campaigns',
            headers=headers, json=body
        )
        if resp.status_code in (200, 207):
            resumed += len(batch)
        else:
            print(f'  Resume batch error: {resp.status_code} {resp.text[:200]}')
    return resumed


def main():
    now = datetime.now()
    tw_hour = now.hour  # Machine is in TW timezone
    print(f'[{now.strftime("%Y-%m-%d %H:%M")}] DAIKEN Budget Guard')
    print(f'Current hour (TW): {tw_hour}')

    env = load_env()
    access_token = get_access_token(env)
    client_id = env['AMAZON_ADS_CLIENT_ID']
    state = load_guard_state()

    # Load pacing data
    if not PACING_JSON.exists():
        print('No pacing data found. Run budget_pacing.py first.')
        return

    pacing = json.loads(PACING_JSON.read_text())
    total_pct = pacing.get('total_pct', 0)
    print(f'MTD pacing: {total_pct:.1f}%')

    # RESUME logic: at 15:00 TW, resume all guard-paused campaigns
    if tw_hour >= RESUME_HOUR_TW and state.get('last_action') == 'paused':
        paused_ids = state.get('paused_campaigns', [])
        if paused_ids:
            print(f'15:00 TW — Resuming {len(paused_ids)} guard-paused campaigns...')
            resumed = resume_campaigns(access_token, client_id, paused_ids)
            print(f'  Resumed {resumed} campaigns')
            state['paused_campaigns'] = []
            state['last_action'] = 'resumed'
            state['last_action_time'] = now.strftime('%Y-%m-%d %H:%M')
            save_guard_state(state)
        else:
            print('No campaigns to resume.')
        return

    # PAUSE logic: if pacing >= 90% and before 15:00, pause all enabled campaigns
    if total_pct >= PAUSE_THRESHOLD and tw_hour < RESUME_HOUR_TW:
        if state.get('last_action') == 'paused':
            print(f'Already paused ({len(state.get("paused_campaigns", []))} campaigns). Skipping.')
            return

        print(f'PACING {total_pct:.0f}% >= {PAUSE_THRESHOLD}% — PAUSING all enabled campaigns!')
        campaigns = fetch_sp_campaigns(access_token, client_id)
        enabled_ids = [c['campaignId'] for c in campaigns if c.get('state') == 'ENABLED']
        print(f'  Found {len(enabled_ids)} enabled campaigns')

        if enabled_ids:
            paused = pause_campaigns(access_token, client_id, enabled_ids)
            print(f'  Paused {paused} campaigns')
            state['paused_campaigns'] = enabled_ids
            state['last_action'] = 'paused'
            state['last_action_time'] = now.strftime('%Y-%m-%d %H:%M')
            save_guard_state(state)
        return

    print(f'Pacing {total_pct:.0f}% < {PAUSE_THRESHOLD}% — no action needed.')
    # If previously paused but pacing dropped (unlikely), keep state


if __name__ == '__main__':
    main()
