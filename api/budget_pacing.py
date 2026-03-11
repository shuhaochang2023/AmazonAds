"""
DAIKEN US — Daily Budget Pacing Tracker
Pulls SP + SB campaign spend from Amazon Ads API, compares to target budgets.
Outputs JSON + updates dashboard HTML executive summary.

Runs via cron: 08:00 + 14:30 Taiwan time daily.
"""

import os
import json
import re
import requests
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / '.env'
PACING_JSON = ROOT / 'api' / 'budget_pacing.json'
DASHBOARD_HTML = ROOT / 'daiken' / 'index.html'

PROFILE_ID = '1243647931853395'  # DAIKEN US

BUDGET_TARGETS = {
    'Kids Fish Oil':    400,
    'Nattokinase':       30,
    'Maca':             160,
    'Bitter Melon':     130,
    'Premium Fish Oil':  30,
    'Lutein':            20,
    'Vitamins':          10,
}
TOTAL_TARGET = sum(BUDGET_TARGETS.values())  # $780 (Option D targets, effective 2026-03-12)

PRODUCT_ZH = {
    'Kids Fish Oil':   '兒童魚油軟糖',
    'Nattokinase':     '納豆激酶',
    'Maca':            '瑪卡',
    'Bitter Melon':    '苦瓜酵素',
    'Premium Fish Oil':'頂級魚油',
    'Lutein':          '葉黃素',
    'Vitamins':        '維生素',
}


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


def categorize_campaign(name):
    nl = name.lower()
    if 'fish oil omega' in nl or ('premium' in nl and 'fish' in nl) or nl.startswith('fish oil omega'):
        return 'Premium Fish Oil'
    if 'fish oil' in nl or 'omega' in nl or 'cod liver' in nl or 'kids fish' in nl:
        return 'Kids Fish Oil'
    if 'natto' in nl or 'multi-enzyme' in nl:
        return 'Nattokinase'
    if 'maca' in nl or 'l-arginine' in nl:
        return 'Maca'
    if 'bitter melon' in nl or 'bitter gourd' in nl:
        return 'Bitter Melon'
    if 'lutein' in nl:
        return 'Lutein'
    if 'vitamin' in nl:
        return 'Vitamins'
    return None


def fetch_sp_campaigns(access_token, client_id):
    """Fetch all SP campaigns with state + budget."""
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
            print(f'SP campaigns error: {resp.status_code} {resp.text[:300]}')
            break
        data = resp.json()
        all_camps.extend(data.get('campaigns', []))
        next_token = data.get('nextToken')
        if not next_token:
            break
    return all_camps


def fetch_sb_campaigns(access_token, client_id):
    """Fetch all SB campaigns."""
    headers = {
        'Amazon-Advertising-API-ClientId': client_id,
        'Amazon-Advertising-API-Scope': PROFILE_ID,
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
        'Accept': 'application/vnd.sbcampaignresource.v4+json',
    }
    resp = requests.post(
        'https://advertising-api.amazon.com/sb/v4/campaigns/list',
        headers=headers, json={'maxResults': 100}
    )
    if resp.status_code == 200:
        return resp.json().get('campaigns', [])
    # Fallback to v3
    headers['Accept'] = 'application/json'
    resp = requests.get(
        'https://advertising-api.amazon.com/sb/campaigns',
        headers=headers, params={'stateFilter': 'enabled,paused', 'count': 100}
    )
    if resp.status_code == 200:
        return resp.json() if isinstance(resp.json(), list) else []
    print(f'SB campaigns error: {resp.status_code} {resp.text[:300]}')
    return []


def create_sp_report(access_token, client_id, start_date, end_date=None):
    """Request an SP campaign-level report for a date range via Reporting API v3."""
    if end_date is None:
        end_date = start_date
    headers = {
        'Amazon-Advertising-API-ClientId': client_id,
        'Amazon-Advertising-API-Scope': PROFILE_ID,
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/vnd.createasyncreportrequest.v3+json',
        'Accept': 'application/vnd.createasyncreportrequest.v3+json',
    }
    body = {
        'name': f'SP Campaign MTD {start_date}_{end_date}_{datetime.now().strftime("%H%M")}',
        'startDate': start_date,
        'endDate': end_date,
        'configuration': {
            'adProduct': 'SPONSORED_PRODUCTS',
            'groupBy': ['campaign'],
            'columns': ['campaignName', 'campaignId', 'campaignStatus',
                        'campaignBudgetAmount', 'spend', 'sales14d',
                        'impressions', 'clicks', 'purchases14d'],
            'reportTypeId': 'spCampaigns',
            'timeUnit': 'SUMMARY',
            'format': 'GZIP_JSON',
        }
    }
    resp = requests.post(
        'https://advertising-api.amazon.com/reporting/reports',
        headers=headers, json=body
    )
    if resp.status_code in (200, 202):
        return resp.json().get('reportId')
    # Handle duplicate: extract existing report ID
    if resp.status_code == 425:
        import re as _re
        match = _re.search(r'duplicate of\s*:\s*([\w-]+)', resp.text)
        if match:
            dup_id = match.group(1)
            print(f'Reusing existing report: {dup_id}')
            return dup_id
    print(f'Report create error: {resp.status_code} {resp.text[:500]}')
    return None


def poll_report(access_token, client_id, report_id, max_wait=120):
    """Poll report status until completed, return download URL."""
    import time
    headers = {
        'Amazon-Advertising-API-ClientId': client_id,
        'Amazon-Advertising-API-Scope': PROFILE_ID,
        'Authorization': f'Bearer {access_token}',
    }
    for i in range(max_wait // 5):
        resp = requests.get(
            f'https://advertising-api.amazon.com/reporting/reports/{report_id}',
            headers=headers
        )
        if resp.status_code == 200:
            data = resp.json()
            status = data.get('status', '')
            if i % 6 == 0:
                print(f'  Status: {status} ({i * 5}s)')
            if status == 'COMPLETED':
                return data.get('url')
            if status == 'FAILURE':
                print(f'Report failed: {data}')
                return None
        time.sleep(5)
    print('Report timed out')
    return None


def download_report(url):
    """Download and decompress a gzipped JSON report."""
    import gzip
    resp = requests.get(url)
    resp.raise_for_status()
    data = gzip.decompress(resp.content)
    return json.loads(data)


def aggregate_spend(report_rows):
    """Group report rows by product category, sum spend."""
    cats = defaultdict(lambda: {
        'spend': 0, 'sales': 0, 'impressions': 0, 'clicks': 0,
        'orders': 0, 'campaigns_active': 0, 'campaigns_paused': 0
    })
    for row in report_rows:
        name = row.get('campaignName', '')
        cat = categorize_campaign(name)
        if cat is None:
            cat = 'Other'
        spend = float(row.get('spend', 0))
        cats[cat]['spend'] += spend
        cats[cat]['sales'] += float(row.get('sales14d', 0) or row.get('sales', 0) or 0)
        cats[cat]['impressions'] += int(row.get('impressions', 0))
        cats[cat]['clicks'] += int(row.get('clicks', 0))
        cats[cat]['orders'] += int(row.get('purchases14d', 0) or 0)
        status = row.get('campaignStatus', '').lower()
        if status == 'enabled':
            cats[cat]['campaigns_active'] += 1
        else:
            cats[cat]['campaigns_paused'] += 1
    return dict(cats)


def build_pacing_data(yesterday_cats, today_cats):
    """Build today's pacing: bar = daily + yesterday's unspent, fill = today's spend."""
    now = datetime.now()
    products = []
    total_today_target = 0
    total_today_spend = 0
    for product, daily_target in BUDGET_TARGETS.items():
        y_spend = round(yesterday_cats.get(product, 0), 2)
        t_spend = round(today_cats.get(product, 0), 2)
        unspent = round(max(daily_target - y_spend, 0), 2)
        today_target = round(daily_target + unspent, 2)
        fill_pct = round(t_spend / today_target * 100, 1) if today_target > 0 else 0
        total_today_target += today_target
        total_today_spend += t_spend
        products.append({
            'product': product,
            'product_zh': PRODUCT_ZH.get(product, ''),
            'daily_target': daily_target,
            'yesterday_spend': y_spend,
            'unspent': unspent,
            'today_target': today_target,
            'today_spend': t_spend,
            'fill_pct': fill_pct,
        })

    return {
        'timestamp': now.strftime('%Y-%m-%d %H:%M'),
        'today': now.strftime('%Y-%m-%d'),
        'yesterday': (now - timedelta(days=1)).strftime('%Y-%m-%d'),
        'total_today_target': round(total_today_target, 2),
        'total_today_spend': round(total_today_spend, 2),
        'total_fill_pct': round(total_today_spend / total_today_target * 100, 1) if total_today_target > 0 else 0,
        'products': products,
    }


def inject_dashboard(pacing):
    """Inject/update the budget pacing widget into the dashboard HTML."""
    html = DASHBOARD_HTML.read_text(encoding='utf-8')

    ts = pacing['timestamp']
    total_tgt = pacing['total_today_target']
    total_spd = pacing['total_today_spend']
    total_fill = pacing['total_fill_pct']

    # Build product bars
    rows_html = ''
    for p in pacing['products']:
        daily = p['daily_target']
        unspent = p['unspent']
        today_tgt = p['today_target']
        today_spd = p['today_spend']
        fill = min(p['fill_pct'], 100)

        # Green fill, red at 95%+
        if p['fill_pct'] >= 95:
            bar_bg = '#dc2626'
            c = '#dc2626'
        elif p['fill_pct'] >= 60:
            bar_bg = '#16a34a'
            c = '#16a34a'
        else:
            bar_bg = '#22c55e'
            c = '#16a34a'

        # Right label: $daily + $unspent = $target
        if unspent > 0:
            right_label = f'${daily:.0f}<span style="color:#dc2626">+{unspent:.0f}</span>=${today_tgt:.0f}'
        else:
            right_label = f'${today_tgt:.0f}'

        rows_html += f'''<div style="display:flex;align-items:center;gap:5px;padding:2px 0">
  <div style="width:44px;font-size:8px;font-weight:600;color:var(--text2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{p['product_zh']}</div>
  <div style="flex:1;position:relative;height:20px;background:#fff;border-radius:4px;overflow:hidden;border:1px solid var(--border)">
    <div style="height:100%;border-radius:3px;background:{bar_bg};width:{fill}%"></div>
    <div style="position:absolute;top:0;left:6px;right:6px;bottom:0;display:flex;align-items:center;justify-content:space-between">
      <span style="font-family:var(--mono);font-size:9px;font-weight:700;color:{'#fff' if fill > 45 else 'var(--text)'}">${today_spd:.0f}</span>
      <span style="font-family:var(--mono);font-size:8px;color:{'rgba(255,255,255,.7)' if fill > 85 else 'var(--text3)'}">${today_tgt:.0f}</span>
    </div>
  </div>
  <div style="width:36px;font-family:var(--mono);font-size:9px;font-weight:700;color:{c};text-align:right">{p['fill_pct']:.0f}%</div>
</div>'''

    widget = f'''<!-- BUDGET PACING WIDGET — auto-generated by budget_pacing.py -->
<style>
@keyframes pacingPulse {{ 0%,100%{{opacity:1}} 50%{{opacity:.35}} }}
</style>
<details id="budget-pacing-widget" open style="background:var(--bg2);border:1px solid var(--border);border-radius:10px;margin-bottom:14px;box-shadow:0 1px 4px rgba(0,0,0,.05)">
  <summary style="padding:10px 18px;cursor:pointer;display:flex;align-items:center;gap:8px;font-family:var(--mono);font-size:11px;font-weight:700;color:var(--accent);list-style:none">
    <span style="font-size:12px">&#9654;</span>
    <span>Today&#39;s Pacing 今日預算執行</span>
    <span style="display:inline-flex;align-items:center;gap:4px;font-size:7px;font-weight:700;color:#16a34a;background:rgba(22,163,74,.1);border:1px solid rgba(34,197,94,.25);padding:1px 5px;border-radius:3px">
      <span style="display:inline-block;width:4px;height:4px;border-radius:50%;background:#16a34a;animation:pacingPulse 1.5s ease-in-out infinite"></span>LIVE
    </span>
    <span style="font-size:10px;color:var(--text3);font-weight:500;margin-left:auto">${total_spd:,.0f} / ${total_tgt:,.0f} ({total_fill:.0f}%) · {ts}</span>
  </summary>
  <div style="padding:2px 18px 14px">
    <div style="font-family:var(--mono);font-size:8px;color:var(--text3);margin-bottom:4px;max-width:520px">
      bar = daily budget + yesterday&#39;s unspent · <span style="color:#16a34a">green</span> = spending · <span style="color:#dc2626">red = 95%+ AUTO-PAUSE</span>
    </div>
    <div style="max-width:520px">
{rows_html}
    </div>
    <div style="font-family:var(--mono);font-size:8px;color:var(--text3);margin-top:4px;border-top:1px solid var(--border);padding-top:3px;max-width:520px">
      &#x1F6D1; 95%+ auto-pause all campaigns · resume 15:00 TW daily
    </div>
  </div>
</details>
<!-- /BUDGET PACING WIDGET -->'''

    # Remove existing widget if present
    html = re.sub(
        r'<!-- BUDGET PACING WIDGET.*?<!-- /BUDGET PACING WIDGET -->\n?',
        '', html, flags=re.DOTALL
    )

    # Insert after the action log </details> and before the KPI strip
    insert_marker = '<!-- Overall Account KPIs -->'
    if insert_marker in html:
        html = html.replace(insert_marker, widget + '\n\n  ' + insert_marker)
    else:
        # Fallback: insert before kpi-exec
        html = html.replace(
            '<div class="kpi-strip" style="margin-bottom:20px" id="kpi-exec">',
            widget + '\n\n  <div class="kpi-strip" style="margin-bottom:20px" id="kpi-exec">'
        )

    DASHBOARD_HTML.write_text(html, encoding='utf-8')
    print(f'Dashboard updated: {DASHBOARD_HTML}')


def pull_day_report(access_token, client_id, date_str, label):
    """Pull a single-day SP report. Returns aggregated spend by category."""
    report_id = create_sp_report(access_token, client_id, date_str, date_str)
    if not report_id:
        print(f'  {label}: failed to create report')
        return {}
    print(f'  {label}: {report_id} — polling...')
    url = poll_report(access_token, client_id, report_id, max_wait=600)
    if not url:
        print(f'  {label}: timed out')
        return {}
    rows = download_report(url)
    print(f'  {label}: {len(rows)} rows')
    cats = aggregate_spend(rows)
    # Flatten to just spend per category
    return {k: v.get('spend', 0) for k, v in cats.items()}


def main():
    print(f'[{datetime.now().strftime("%Y-%m-%d %H:%M")}] DAIKEN Daily Pacing')
    print('=' * 60)

    env = load_env()
    access_token = get_access_token(env)
    client_id = env['AMAZON_ADS_CLIENT_ID']

    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    today = datetime.now().strftime('%Y-%m-%d')

    print(f'Pulling yesterday ({yesterday}) + today ({today})...')
    y_cats = pull_day_report(access_token, client_id, yesterday, 'yesterday')
    t_cats = pull_day_report(access_token, client_id, today, 'today')

    if not y_cats and not t_cats:
        print('Both reports failed. Exiting.')
        return

    pacing = build_pacing_data(y_cats, t_cats)

    # Save JSON
    PACING_JSON.write_text(json.dumps(pacing, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'Saved: {PACING_JSON}')

    # Print summary
    print(f'\n{"Product":<20} {"Daily":>6} {"Yday":>8} {"Unspent":>8} {"TodayTgt":>9} {"TodaySpd":>9} {"Fill%":>6}')
    print('-' * 72)
    for p in pacing['products']:
        print(f'{p["product"]:<20} ${p["daily_target"]:>5} ${p["yesterday_spend"]:>7.0f} ${p["unspent"]:>7.0f} ${p["today_target"]:>8.0f} ${p["today_spend"]:>8.0f} {p["fill_pct"]:>5.0f}%')
    print('-' * 72)
    print(f'{"TOTAL":<20} ${sum(BUDGET_TARGETS.values()):>5} {"":>8} {"":>8} ${pacing["total_today_target"]:>8.0f} ${pacing["total_today_spend"]:>8.0f} {pacing["total_fill_pct"]:>5.0f}%')

    # Update dashboard
    inject_dashboard(pacing)

    # Git push
    os.chdir(ROOT)
    os.system('git add daiken/index.html api/budget_pacing.json')
    os.system(f'git commit -m "DAIKEN: daily pacing {pacing["timestamp"]}"')
    os.system('git push origin main')
    print('\nDone — dashboard deployed.')


if __name__ == '__main__':
    main()
