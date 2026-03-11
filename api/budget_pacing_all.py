"""
Multi-Brand Daily Budget Pacing Tracker
Pulls SP campaign spend from Amazon Ads API for all brands,
compares to target budgets, injects collapsible pacing widget into each dashboard.

Cron: 08:00 + 14:30 Taiwan time daily.
"""

import os
import json
import re
import gzip
import time
import requests
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / '.env'
CONFIG_PATH = ROOT / 'api' / 'brand_pacing_config.json'
PACING_DIR = ROOT / 'api'

# Also run DAIKEN (original config kept in budget_pacing.py)
DAIKEN_CONFIG = {
    'profile_id': '1243647931853395',
    'dashboard': 'daiken/index.html',
    'total_target': 780,
    'tacos_target': 70,
    'products': {
        'Kids Fish Oil':    {'target': 400, 'zh': '兒童魚油軟糖'},
        'Nattokinase':      {'target': 90,  'zh': '納豆激酶'},
        'Maca':             {'target': 130, 'zh': '瑪卡'},
        'Bitter Melon':     {'target': 100, 'zh': '苦瓜酵素'},
        'Premium Fish Oil': {'target': 30,  'zh': '頂級魚油'},
        'Lutein':           {'target': 20,  'zh': '葉黃素'},
        'Vitamins':         {'target': 10,  'zh': '維生素'},
    },
    'categorize_rules': [
        {'match': ['fish oil omega', 'premium fish', 'b0cvth'], 'cat': 'Premium Fish Oil'},
        {'match': ['fish oil', 'omega', 'cod liver', 'kids fish'], 'cat': 'Kids Fish Oil'},
        {'match': ['natto', 'multi-enzyme'], 'cat': 'Nattokinase'},
        {'match': ['maca', 'l-arginine'], 'cat': 'Maca'},
        {'match': ['bitter melon', 'bitter gourd'], 'cat': 'Bitter Melon'},
        {'match': ['lutein'], 'cat': 'Lutein'},
        {'match': ['vitamin'], 'cat': 'Vitamins'},
    ],
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


def categorize_campaign(name, config):
    nl = name.lower()
    for rule in config.get('categorize_rules', []):
        if any(m in nl for m in rule['match']):
            return rule['cat']
    return config.get('default_cat', 'Other')


def create_report(access_token, client_id, profile_id, date_str, brand_name):
    headers = {
        'Amazon-Advertising-API-ClientId': client_id,
        'Amazon-Advertising-API-Scope': str(profile_id),
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/vnd.createasyncreportrequest.v3+json',
        'Accept': 'application/vnd.createasyncreportrequest.v3+json',
    }
    body = {
        'name': f'{brand_name} Pacing {date_str}',
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
    resp = requests.post('https://advertising-api.amazon.com/reporting/reports',
                         headers=headers, json=body)
    if resp.status_code in (200, 202):
        return resp.json().get('reportId')
    if resp.status_code == 425:
        match = re.search(r'duplicate of\s*:\s*([\w-]+)', resp.text)
        if match:
            return match.group(1)
    print(f'    Report create error: {resp.status_code} {resp.text[:200]}')
    return None


def poll_report(access_token, client_id, profile_id, report_id, max_wait=300):
    headers = {
        'Amazon-Advertising-API-ClientId': client_id,
        'Amazon-Advertising-API-Scope': str(profile_id),
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
            if status == 'COMPLETED':
                return data.get('url')
            if status == 'FAILURE':
                print(f'    Report failed')
                return None
        time.sleep(5)
    print(f'    Report timed out')
    return None


def download_report(url):
    resp = requests.get(url)
    resp.raise_for_status()
    return json.loads(gzip.decompress(resp.content))


def process_brand(brand_name, config, rows):
    products = config['products']
    cats = defaultdict(lambda: {'spend': 0, 'sales': 0, 'orders': 0})

    for row in rows:
        name = row.get('campaignName', '')
        cat = categorize_campaign(name, config)
        spend = float(row.get('spend', 0) or 0)
        sales = float(row.get('sales14d', 0) or 0)
        orders = int(float(row.get('purchases14d', 0) or 0))
        cats[cat]['spend'] += spend
        cats[cat]['sales'] += sales
        cats[cat]['orders'] += orders

    now = datetime.now()
    yesterday = (now - timedelta(days=1)).strftime('%Y-%m-%d')
    total_target = config['total_target']

    product_list = []
    total_spend = 0
    for product_name, pconfig in products.items():
        target = pconfig['target']
        data = cats.get(product_name, {})
        spend = round(data.get('spend', 0), 2)
        total_spend += spend
        diff = round(spend - target, 2)
        pct = round(spend / target * 100, 1) if target > 0 else 0
        status = 'on_track' if 80 <= pct <= 120 else ('over' if pct > 120 else 'under')
        product_list.append({
            'product': product_name,
            'product_zh': pconfig.get('zh', ''),
            'spend': spend,
            'target': target,
            'diff': diff,
            'pct': pct,
            'status': status,
            'sales': round(data.get('sales', 0), 2),
            'orders': int(data.get('orders', 0)),
        })

    # Include uncategorized spend
    other_spend = sum(v['spend'] for k, v in cats.items() if k not in products and k != 'Other')
    if 'Other' not in products:
        total_spend += round(other_spend, 2)

    total_pct = round(total_spend / total_target * 100, 1) if total_target else 0

    return {
        'brand': brand_name,
        'timestamp': now.strftime('%Y-%m-%d %H:%M'),
        'report_date': yesterday,
        'total_spend': round(total_spend, 2),
        'total_target': total_target,
        'total_pct': total_pct,
        'products': product_list,
    }


def build_widget_html(pacing):
    ts = pacing['timestamp']
    rdate = pacing['report_date']

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

    total_pct = min(pacing['total_pct'], 100)
    total_diff = pacing['total_spend'] - pacing['total_target']
    total_sign = '+' if total_diff >= 0 else ''
    if abs(pacing['total_pct'] - 100) <= 20:
        t_grad = 'linear-gradient(90deg,#2563eb,#60a5fa)'
    elif pacing['total_pct'] > 120:
        t_grad = 'linear-gradient(90deg,#dc2626,#f87171)'
    else:
        t_grad = 'linear-gradient(90deg,#d97706,#fbbf24)'

    return f'''<!-- BUDGET PACING WIDGET — auto-generated by budget_pacing_all.py -->
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
    <div style="position:relative;height:22px;background:var(--bg);border-radius:6px;overflow:hidden;border:1px solid var(--border);margin-bottom:4px;max-width:520px">
      <div style="height:100%;border-radius:5px;background:{t_grad};width:{total_pct}%;position:relative;overflow:hidden">
        <div style="position:absolute;top:0;left:0;right:0;bottom:0;background:linear-gradient(90deg,transparent,rgba(255,255,255,.3),transparent);animation:pacingShimmer 2.5s infinite"></div>
      </div>
      <div style="position:absolute;top:0;left:0;right:0;bottom:0;display:flex;align-items:center;justify-content:center">
        <span style="font-family:var(--mono);font-size:11px;font-weight:800;color:var(--text);text-shadow:0 0 3px rgba(255,255,255,.9)">${pacing['total_spend']:,.0f} / ${pacing['total_target']:,.0f} ({pacing['total_pct']:.0f}%)</span>
      </div>
    </div>
    <div style="font-family:var(--mono);font-size:9px;color:var(--text3);text-align:right;margin-bottom:10px;max-width:520px">gap: {total_sign}${total_diff:,.0f} · updated {ts} · cron 08:00 + 14:30</div>
    <div style="max-width:520px">{rows_html}</div>
  </div>
</details>
<!-- /BUDGET PACING WIDGET -->'''


def inject_widget(dashboard_path, widget_html):
    html = dashboard_path.read_text(encoding='utf-8')

    # Remove existing widget
    html = re.sub(
        r'<!-- BUDGET PACING WIDGET.*?<!-- /BUDGET PACING WIDGET -->\n?',
        '', html, flags=re.DOTALL
    )

    # Insert before KPI strip or action log
    for marker in ['<!-- Overall Account KPIs -->',
                    '<div class="kpi-strip"',
                    '<div class="sec-header">']:
        if marker in html:
            html = html.replace(marker, widget_html + '\n\n  ' + marker, 1)
            break

    dashboard_path.write_text(html, encoding='utf-8')


def main():
    now = datetime.now()
    print(f'[{now.strftime("%Y-%m-%d %H:%M")}] Multi-Brand Budget Pacing')
    print('=' * 60)

    env = load_env()
    access_token = get_access_token(env)
    client_id = env['AMAZON_ADS_CLIENT_ID']
    yesterday = (now - timedelta(days=1)).strftime('%Y-%m-%d')

    # Load brand configs
    with open(CONFIG_PATH) as f:
        brand_configs = json.load(f)

    # Add DAIKEN
    brand_configs['DAIKEN'] = DAIKEN_CONFIG

    all_pacing = {}
    dashboards_updated = []

    for brand_name, config in brand_configs.items():
        profile_id = config['profile_id']
        print(f'\n--- {brand_name} (profile {profile_id}) ---')

        # Create report
        report_id = create_report(access_token, client_id, profile_id, yesterday, brand_name)
        if not report_id:
            print(f'  Skipping {brand_name}')
            continue

        print(f'  Report {report_id} — polling...')
        url = poll_report(access_token, client_id, profile_id, report_id)
        if not url:
            print(f'  Skipping {brand_name}')
            continue

        rows = download_report(url)
        print(f'  {len(rows)} campaigns')

        # Process
        pacing = process_brand(brand_name, config, rows)
        all_pacing[brand_name] = pacing

        # Print summary
        print(f'  Total: ${pacing["total_spend"]:,.0f} / ${pacing["total_target"]:,.0f} ({pacing["total_pct"]:.0f}%)')
        for p in pacing['products']:
            sign = '+' if p['diff'] >= 0 else ''
            print(f'    {p["product"]:<20} ${p["spend"]:>6,.0f} / ${p["target"]:>4,.0f}  {p["pct"]:>5.0f}%  {sign}${p["diff"]:>5,.0f}')

        # Inject widget into dashboard
        dashboard = ROOT / config['dashboard']
        if dashboard.exists():
            widget = build_widget_html(pacing)
            inject_widget(dashboard, widget)
            dashboards_updated.append(str(dashboard))
            print(f'  Dashboard updated: {dashboard.name}')

    # Save all pacing data
    pacing_file = PACING_DIR / 'budget_pacing_all.json'
    with open(pacing_file, 'w') as f:
        json.dump(all_pacing, f, indent=2, ensure_ascii=False)
    print(f'\nSaved: {pacing_file}')

    # Git commit + push
    if dashboards_updated:
        os.chdir(ROOT)
        # Stage all updated dashboards + JSON
        files = ' '.join(f'"{d}"' for d in dashboards_updated)
        os.system(f'git add {files} api/budget_pacing_all.json')
        ts = now.strftime('%Y-%m-%d %H:%M')
        brands_str = ', '.join(all_pacing.keys())
        os.system(f'git commit -m "Budget pacing update {ts} — {brands_str}"')
        os.system('git push origin main')
        print('\nDashboards deployed.')

    print(f'\nDone — {len(all_pacing)} brands processed.')


if __name__ == '__main__':
    main()
