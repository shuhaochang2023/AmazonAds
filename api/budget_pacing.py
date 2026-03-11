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
    'Nattokinase':       90,
    'Maca':             130,
    'Bitter Melon':     100,
    'Premium Fish Oil':  30,
    'Lutein':            20,
    'Vitamins':          10,
}
TOTAL_TARGET = sum(BUDGET_TARGETS.values())  # $780 (client original targets)

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


def build_pacing_data(cats):
    """Compare MTD spend to MTD targets (daily budget × days elapsed)."""
    now = datetime.now()
    days_elapsed = (now - timedelta(days=1)).day  # through yesterday
    days_in_month = 31 if now.month == 3 else 30  # simplify
    products = []
    total_spend = 0
    total_mtd_target = 0
    total_month_target = 0
    for product, daily_target in BUDGET_TARGETS.items():
        data = cats.get(product, {})
        spend = round(data.get('spend', 0), 2)
        total_spend += spend
        mtd_target = round(daily_target * days_elapsed, 2)
        month_target = round(daily_target * days_in_month, 2)
        total_mtd_target += mtd_target
        total_month_target += month_target
        diff = round(spend - mtd_target, 2)
        pct = round(spend / mtd_target * 100, 1) if mtd_target > 0 else 0
        status = 'on_track'
        if pct > 120:
            status = 'over'
        elif pct < 80:
            status = 'under'
        products.append({
            'product': product,
            'product_zh': PRODUCT_ZH.get(product, ''),
            'spend': spend,
            'target': mtd_target,
            'month_target': month_target,
            'diff': diff,
            'pct': pct,
            'status': status,
            'sales': round(data.get('sales', 0), 2),
            'orders': int(data.get('orders', 0)),
        })

    other_spend = round(cats.get('Other', {}).get('spend', 0), 2)

    return {
        'timestamp': now.strftime('%Y-%m-%d %H:%M'),
        'report_date': now.strftime('%Y-%m-%d'),
        'days_elapsed': days_elapsed,
        'days_in_month': days_in_month,
        'total_spend': round(total_spend + other_spend, 2),
        'total_target': round(total_mtd_target, 2),
        'total_month_target': round(total_month_target, 2),
        'total_pct': round((total_spend + other_spend) / total_mtd_target * 100, 1) if total_mtd_target else 0,
        'products': products,
        'other_spend': other_spend,
    }


def inject_dashboard(pacing):
    """Inject/update the budget pacing widget into the dashboard HTML."""
    html = DASHBOARD_HTML.read_text(encoding='utf-8')

    ts = pacing['timestamp']
    rdate = pacing['report_date']
    days_elapsed = pacing.get('days_elapsed', 10)
    days_in_month = pacing.get('days_in_month', 31)

    # Build compact product rows
    rows_html = ''
    for p in pacing['products']:
        if p['status'] == 'on_track':
            bar_bg = 'linear-gradient(90deg,#16a34a,#22c55e)'
            c = '#16a34a'
        elif p['status'] == 'over':
            bar_bg = 'linear-gradient(90deg,#dc2626,#f87171)'
            c = '#dc2626'
        else:
            bar_bg = 'linear-gradient(90deg,#d97706,#fbbf24)'
            c = '#d97706'

        bar_pct = min(p['pct'], 100)
        sign = '+' if p['diff'] >= 0 else ''

        rows_html += f'''<div style="display:flex;align-items:center;gap:8px;padding:4px 0">
  <div style="width:62px;font-size:11px;font-weight:600;color:var(--text);white-space:nowrap;overflow:hidden">{p['product_zh']}</div>
  <div style="flex:1;position:relative;height:16px;background:var(--bg);border-radius:4px;overflow:hidden;border:1px solid var(--border)">
    <div style="height:100%;border-radius:3px;background:{bar_bg};width:{bar_pct}%;position:relative;overflow:hidden">
      <div style="position:absolute;top:0;left:0;right:0;bottom:0;background:linear-gradient(90deg,transparent,rgba(255,255,255,.25),transparent);animation:pacingShimmer 2s infinite"></div>
    </div>
  </div>
  <div style="width:36px;font-family:var(--mono);font-size:10px;font-weight:700;color:{c};text-align:right">{p['pct']:.0f}%</div>
  <div style="width:70px;font-family:var(--mono);font-size:10px;color:var(--text2);text-align:right">${p['spend']:,.0f}/${p['target']:,.0f}</div>
</div>'''

    # Total
    total_pct = min(pacing['total_pct'], 100)
    total_diff = pacing['total_spend'] - pacing['total_target']
    total_sign = '+' if total_diff >= 0 else ''
    if abs(pacing['total_pct'] - 100) <= 20:
        t_grad = 'linear-gradient(90deg,#2563eb,#60a5fa)'
        t_c = '#2563eb'
    elif pacing['total_pct'] > 120:
        t_grad = 'linear-gradient(90deg,#dc2626,#f87171)'
        t_c = '#dc2626'
    else:
        t_grad = 'linear-gradient(90deg,#d97706,#fbbf24)'
        t_c = '#d97706'

    widget = f'''<!-- BUDGET PACING WIDGET — auto-generated by budget_pacing.py -->
<style>
@keyframes pacingShimmer {{ 0%{{transform:translateX(-100%)}} 100%{{transform:translateX(100%)}} }}
@keyframes pacingPulse {{ 0%,100%{{opacity:1}} 50%{{opacity:.35}} }}
</style>
<details id="budget-pacing-widget" style="background:var(--bg2);border:1px solid var(--border);border-radius:10px;margin-bottom:14px;box-shadow:0 1px 4px rgba(0,0,0,.05)">
  <summary style="padding:12px 18px;cursor:pointer;display:flex;align-items:center;gap:10px;font-family:var(--mono);font-size:12px;font-weight:700;color:var(--accent);list-style:none">
    <span style="font-size:14px;transition:transform .2s;display:inline-block">&#9654;</span>
    <span>Budget Pacing 預算執行追蹤</span>
    <span style="display:inline-flex;align-items:center;gap:4px;font-size:8px;font-weight:700;color:#16a34a;background:rgba(22,163,74,.1);border:1px solid rgba(34,197,94,.25);padding:2px 6px;border-radius:3px">
      <span style="display:inline-block;width:5px;height:5px;border-radius:50%;background:#16a34a;animation:pacingPulse 1.5s ease-in-out infinite"></span>LIVE
    </span>
    <span style="font-size:11px;color:var(--text3);font-weight:500;margin-left:auto">${pacing['total_spend']:,.0f} / ${pacing['total_target']:,.0f} ({pacing['total_pct']:.0f}%) · {rdate}</span>
  </summary>
  <div style="padding:4px 18px 18px">

    <!-- Total bar -->
    <div style="position:relative;height:22px;background:var(--bg);border-radius:6px;overflow:hidden;border:1px solid var(--border);margin-bottom:4px;max-width:520px">
      <div style="height:100%;border-radius:5px;background:{t_grad};width:{total_pct}%;position:relative;overflow:hidden">
        <div style="position:absolute;top:0;left:0;right:0;bottom:0;background:linear-gradient(90deg,transparent,rgba(255,255,255,.3),transparent);animation:pacingShimmer 2.5s infinite"></div>
      </div>
      <div style="position:absolute;top:0;left:0;right:0;bottom:0;display:flex;align-items:center;justify-content:center">
        <span style="font-family:var(--mono);font-size:11px;font-weight:800;color:var(--text);text-shadow:0 0 3px rgba(255,255,255,.9)">${pacing['total_spend']:,.0f} / ${pacing['total_target']:,.0f} ({pacing['total_pct']:.0f}%)</span>
      </div>
    </div>
    <div style="font-family:var(--mono);font-size:9px;color:var(--text3);text-align:right;margin-bottom:10px;max-width:520px">gap: {total_sign}${total_diff:,.0f} · MTD day {days_elapsed}/{days_in_month} · updated {ts}</div>

    <!-- Product bars -->
    <div style="max-width:520px">
      {rows_html}
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


def main():
    print(f'[{datetime.now().strftime("%Y-%m-%d %H:%M")}] DAIKEN Budget Pacing Check')
    print('=' * 60)

    env = load_env()
    access_token = get_access_token(env)
    client_id = env['AMAZON_ADS_CLIENT_ID']

    # MTD: March 1 through yesterday (today's data is incomplete)
    month_start = datetime.now().replace(day=1).strftime('%Y-%m-%d')
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    print(f'Pulling SP report for {month_start} to {yesterday} (MTD)...')

    report_id = create_sp_report(access_token, client_id, month_start, end_date=yesterday)
    if not report_id:
        print('Failed to create report. Exiting.')
        return

    print(f'Report ID: {report_id} — polling...')
    url = poll_report(access_token, client_id, report_id, max_wait=300)
    if not url:
        print('Failed to get report. Exiting.')
        return

    rows = download_report(url)
    print(f'Downloaded {len(rows)} campaign rows')

    cats = aggregate_spend(rows)
    pacing = build_pacing_data(cats)

    # Save JSON
    PACING_JSON.write_text(json.dumps(pacing, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'Saved: {PACING_JSON}')

    # Print summary
    print(f'\nMTD through day {pacing["days_elapsed"]}/{pacing["days_in_month"]}')
    print(f'{"Product":<20} {"MTD Spend":>10} {"MTD Tgt":>10} {"Pct":>8} {"Gap":>10} {"Status"}')
    print('-' * 72)
    for p in pacing['products']:
        sign = '+' if p['diff'] >= 0 else ''
        print(f'{p["product"]:<20} ${p["spend"]:>8,.0f} ${p["target"]:>8,.0f} {p["pct"]:>7.0f}% {sign}${p["diff"]:>7,.0f}  {p["status"]}')
    print('-' * 72)
    print(f'{"TOTAL":<20} ${pacing["total_spend"]:>8,.0f} ${pacing["total_target"]:>8,.0f} {pacing["total_pct"]:>7.0f}%')
    print(f'Month target: ${pacing["total_month_target"]:,.0f}')

    # Update dashboard
    inject_dashboard(pacing)

    # Git push
    os.chdir(ROOT)
    os.system('git add daiken/index.html api/budget_pacing.json')
    os.system(f'git commit -m "DAIKEN: budget pacing update {pacing["timestamp"]}"')
    os.system('git push origin main')
    print('\nDone — dashboard deployed.')


if __name__ == '__main__':
    main()
