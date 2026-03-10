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
TOTAL_TARGET = sum(BUDGET_TARGETS.values())  # $780

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


def create_sp_report(access_token, client_id, date_str):
    """Request an SP campaign-level report for a date via Reporting API v3."""
    headers = {
        'Amazon-Advertising-API-ClientId': client_id,
        'Amazon-Advertising-API-Scope': PROFILE_ID,
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/vnd.createasyncreportrequest.v3+json',
        'Accept': 'application/vnd.createasyncreportrequest.v3+json',
    }
    body = {
        'name': f'SP Campaign Daily Spend {date_str}',
        'startDate': date_str,
        'endDate': date_str,
        'configuration': {
            'adProduct': 'SPONSORED_PRODUCTS',
            'groupBy': ['campaign'],
            'columns': ['campaignName', 'campaignId', 'campaignStatus',
                        'campaignBudgetAmount', 'spend', 'sales14d',
                        'impressions', 'clicks', 'purchases14d'],
            'reportTypeId': 'spCampaigns',
            'timeUnit': 'DAILY',
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
    """Compare spend to targets, compute pacing metrics."""
    now = datetime.now()
    products = []
    total_spend = 0
    for product, target in BUDGET_TARGETS.items():
        data = cats.get(product, {})
        spend = round(data.get('spend', 0), 2)
        total_spend += spend
        diff = round(spend - target, 2)
        pct = round(spend / target * 100, 1) if target > 0 else 0
        status = 'on_track'
        if pct > 120:
            status = 'over'
        elif pct < 80:
            status = 'under'
        products.append({
            'product': product,
            'product_zh': PRODUCT_ZH.get(product, ''),
            'spend': spend,
            'target': target,
            'diff': diff,
            'pct': pct,
            'status': status,
            'sales': round(data.get('sales', 0), 2),
            'orders': int(data.get('orders', 0)),
        })

    other_spend = round(cats.get('Other', {}).get('spend', 0), 2)

    return {
        'timestamp': now.strftime('%Y-%m-%d %H:%M'),
        'report_date': (now - timedelta(days=1)).strftime('%Y-%m-%d'),
        'total_spend': round(total_spend + other_spend, 2),
        'total_target': TOTAL_TARGET,
        'total_pct': round((total_spend + other_spend) / TOTAL_TARGET * 100, 1) if TOTAL_TARGET else 0,
        'products': products,
        'other_spend': other_spend,
    }


def inject_dashboard(pacing):
    """Inject/update the budget pacing widget into the dashboard HTML."""
    html = DASHBOARD_HTML.read_text(encoding='utf-8')

    # Build the pacing widget HTML
    ts = pacing['timestamp']
    rdate = pacing['report_date']
    rows_html = ''
    for p in pacing['products']:
        color = 'var(--green)' if p['status'] == 'on_track' else 'var(--red)' if p['status'] == 'over' else 'var(--amber)'
        arrow = '→' if p['status'] == 'on_track' else '▲' if p['status'] == 'over' else '▼'
        sign = '+' if p['diff'] >= 0 else ''
        bar_w = min(p['pct'], 150)
        rows_html += f'''<tr>
<td style="font-family:var(--body);font-size:13px;text-align:left">{p['product_zh']}<br><span style="font-size:10px;color:var(--text3)">{p['product']}</span></td>
<td style="font-family:var(--mono);font-weight:700">${p['spend']:,.0f}</td>
<td style="font-family:var(--mono);color:var(--text2)">${p['target']:,.0f}</td>
<td><div style="background:var(--bg);border-radius:3px;height:14px;width:80px;position:relative"><div style="background:{color};height:100%;border-radius:3px;width:{bar_w * 80 / 150:.0f}px"></div><span style="position:absolute;right:4px;top:-1px;font-size:9px;font-family:var(--mono);color:var(--text2)">{p['pct']:.0f}%</span></div></td>
<td style="font-family:var(--mono);color:{color};font-size:12px;font-weight:600">{arrow} {sign}${p['diff']:,.0f}</td>
<td style="font-family:var(--mono);font-size:11px">${p['sales']:,.0f}</td>
<td style="font-family:var(--mono);font-size:11px">{p['orders']}</td>
</tr>'''

    total_color = 'var(--green)' if abs(pacing['total_pct'] - 100) <= 20 else 'var(--red)' if pacing['total_pct'] > 120 else 'var(--amber)'
    total_diff = pacing['total_spend'] - pacing['total_target']
    total_sign = '+' if total_diff >= 0 else ''

    widget = f'''<!-- BUDGET PACING WIDGET — auto-generated by budget_pacing.py -->
<div id="budget-pacing-widget" style="background:var(--bg2);border:1px solid var(--border);border-radius:10px;margin-bottom:14px;padding:18px;box-shadow:0 1px 4px rgba(0,0,0,.05)">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px">
    <div>
      <div style="font-family:var(--mono);font-size:12px;font-weight:700;color:var(--accent)">BUDGET PACING 預算執行追蹤</div>
      <div style="font-size:11px;color:var(--text3);margin-top:2px">Report date: {rdate} · Updated: {ts} TWN</div>
    </div>
    <div style="display:flex;gap:10px;align-items:center">
      <div style="font-family:var(--mono);font-size:18px;font-weight:800;color:{total_color}">${pacing['total_spend']:,.0f}<span style="font-size:12px;color:var(--text3);font-weight:500"> / ${pacing['total_target']:,.0f}</span></div>
      <div style="font-family:var(--mono);font-size:11px;color:{total_color};background:rgba(0,0,0,.04);padding:3px 8px;border-radius:4px">{pacing['total_pct']:.0f}% {total_sign}${total_diff:,.0f}</div>
    </div>
  </div>
  <div class="table-wrap">
    <table style="min-width:auto">
      <thead><tr>
        <th style="text-align:left">產品 Product</th><th>日均花費 Spend</th><th>目標 Target</th><th>達成率</th><th>差額 Gap</th><th>銷售 Sales</th><th>訂單</th>
      </tr></thead>
      <tbody>{rows_html}</tbody>
    </table>
  </div>
</div>
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

    # Use yesterday's date for the report (today's data is incomplete)
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    print(f'Pulling SP report for {yesterday}...')

    report_id = create_sp_report(access_token, client_id, yesterday)
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
    print(f'\n{"Product":<20} {"Spend":>10} {"Target":>10} {"Pct":>8} {"Gap":>10} {"Status"}')
    print('-' * 68)
    for p in pacing['products']:
        sign = '+' if p['diff'] >= 0 else ''
        print(f'{p["product"]:<20} ${p["spend"]:>8,.0f} ${p["target"]:>8,.0f} {p["pct"]:>7.0f}% {sign}${p["diff"]:>7,.0f}  {p["status"]}')
    print('-' * 68)
    print(f'{"TOTAL":<20} ${pacing["total_spend"]:>8,.0f} ${pacing["total_target"]:>8,.0f} {pacing["total_pct"]:>7.0f}%')

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
