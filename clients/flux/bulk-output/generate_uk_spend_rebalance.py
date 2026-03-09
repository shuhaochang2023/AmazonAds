#!/usr/bin/env python3
"""
UK Ad Spend Rebalance — Grow good performers, add campaigns for under-invested products.

Strategy based on current sales data:
┌────────────────────────────┬──────────┬─────────┬──────────────────────────────────┐
│ Product                    │ TACOS    │ 5W Sales│ Action                           │
├────────────────────────────┼──────────┼─────────┼──────────────────────────────────┤
│ Avento                     │ 22.2%    │ £4,188  │ SCALE — increase budget +50%     │
│ Verano                     │ 21.0%    │ £421    │ SCALE — 2x budget, add KWs       │
│ Dynamic                    │ 11.7%    │ £210    │ SCALE — new manual campaign       │
│ Ventura                    │  6.9%    │ £100    │ NEW — launch SP Auto+Manual       │
│ Laso-17                    │ 13.8%    │ £69     │ NEW — launch SP Auto              │
│ Wire Strap (80Days 102)    │ 12.2%    │ £142    │ NEW — launch SP Auto              │
│ Sportech                   │ 40.7%    │ £1,787  │ HOLD — W5 improving to 33.5%     │
│ Jet II                     │ 52.7%    │ £490    │ HOLD — spring deal running        │
│ Nylon Strap (80Days 101)   │ 34.7%    │ £2,828  │ REDUCE — slightly over target     │
│ 80Days Pilot               │ 69.6%    │ £1,097  │ CUT — W5 TACOS 96.7%, losing £   │
│ 80Days Women's Oval        │101.6%    │ £240    │ CUT — pure loss                   │
│ 80Days Round               │ 50.3%    │ £40     │ CUT — zero W5 sales               │
└────────────────────────────┴──────────┴─────────┴──────────────────────────────────┘

NOTE: Pause/reduce of existing campaigns requires Campaign IDs from UK bulk download.
      This file creates NEW campaigns for under-invested good performers.
      Ask Eric to download UK bulk xlsx for pause operations.
"""

import openpyxl
from openpyxl.utils import get_column_letter

TIMESTAMP = '20260310_1500'

SP_HEADERS = [
    'Product', 'Entity', 'Operation', 'Campaign ID', 'Ad Group ID',
    'Portfolio ID', 'Ad ID', 'Keyword ID', 'Product Targeting ID',
    'Campaign Name', 'Ad Group Name',
    'Campaign Name (Informational only)', 'Ad Group Name (Informational only)',
    'Portfolio Name (Informational only)', 'Start Date', 'End Date',
    'Targeting Type', 'State',
    'Campaign State (Informational only)', 'Ad Group State (Informational only)',
    'Daily Budget', 'SKU', 'ASIN (Informational only)',
    'Eligibility Status (Informational only)',
    'Reason for Ineligibility (Informational only)',
    'Ad Group Default Bid', 'Ad Group Default Bid (Informational only)', 'Bid',
    'Keyword Text', 'Native Language Keyword', 'Native Language Locale',
    'Match Type', 'Bidding Strategy', 'Placement', 'Percentage',
    'Product Targeting Expression',
    'Resolved Product Targeting Expression (Informational only)',
    'Audience ID', 'Shopper Cohort Percentage', 'Shopper Cohort Type',
    'Segment Name (Informational only)',
    'Impressions', 'Clicks', 'Click-through Rate', 'Spend', 'Sales',
    'Orders', 'Units', 'Conversion Rate', 'ACOS', 'CPC', 'ROAS',
]

SP_ID_COLS = [3, 4, 5, 6, 7, 8]


def set_id_format(ws, id_col_indices, max_row):
    for col_idx in id_col_indices:
        col_letter = get_column_letter(col_idx + 1)
        for row in range(1, max_row + 1):
            ws[f'{col_letter}{row}'].number_format = '@'


def write_sheet(wb, sheet_name, headers, rows, id_col_indices):
    ws = wb.active
    ws.title = sheet_name
    for col_idx, header in enumerate(headers, 1):
        ws.cell(row=1, column=col_idx, value=header)
    for row_idx, row_data in enumerate(rows, 2):
        for col_idx, header in enumerate(headers, 1):
            val = row_data.get(header, '')
            ws.cell(row=row_idx, column=col_idx, value=val)
    set_id_format(ws, id_col_indices, len(rows) + 1)


def make_campaign_row(campaign_name, daily_budget, targeting_type='Auto'):
    row = {h: '' for h in SP_HEADERS}
    row['Product'] = 'Sponsored Products'
    row['Entity'] = 'Campaign'
    row['Operation'] = 'Create'
    row['Campaign ID'] = campaign_name
    row['Campaign Name'] = campaign_name
    row['State'] = 'enabled'
    row['Daily Budget'] = daily_budget
    row['Targeting Type'] = targeting_type
    row['Bidding Strategy'] = 'Dynamic bids - down only'
    return row


def make_ad_group_row(campaign_name, ad_group_name, default_bid):
    row = {h: '' for h in SP_HEADERS}
    row['Product'] = 'Sponsored Products'
    row['Entity'] = 'Ad Group'
    row['Operation'] = 'Create'
    row['Campaign ID'] = campaign_name
    row['Ad Group ID'] = ad_group_name
    row['Ad Group Name'] = ad_group_name
    row['State'] = 'enabled'
    row['Ad Group Default Bid'] = default_bid
    return row


def make_product_ad_row(campaign_name, ad_group_name, sku):
    row = {h: '' for h in SP_HEADERS}
    row['Product'] = 'Sponsored Products'
    row['Entity'] = 'Product Ad'
    row['Operation'] = 'Create'
    row['Campaign ID'] = campaign_name
    row['Ad Group ID'] = ad_group_name
    row['SKU'] = sku
    row['State'] = 'enabled'
    return row


def make_keyword_row(campaign_name, ad_group_name, keyword, match_type, bid):
    row = {h: '' for h in SP_HEADERS}
    row['Product'] = 'Sponsored Products'
    row['Entity'] = 'Keyword'
    row['Operation'] = 'Create'
    row['Campaign ID'] = campaign_name
    row['Ad Group ID'] = ad_group_name
    row['Keyword Text'] = keyword
    row['Match Type'] = match_type
    row['Bid'] = bid
    row['State'] = 'enabled'
    return row


rows = []

# ═══════════════════════════════════════════════════════════════
# 1. AVENTO — SCALE UP (22.2% TACOS, £4,188 sales, W5 +38%)
#    Already has spring deal campaigns at £57/day.
#    Adding a separate Exact Match campaign to capture high-intent traffic.
# ═══════════════════════════════════════════════════════════════

avento_children = [
    ('B07G8WDT6H', 'Avento-Black'),       # £2,059 5W, best seller
    ('B07G8SL62W', 'Avento-Red'),          # £659
    ('B0C2P48NCR', 'AVENTO-BLK-Blue'),     # £560
    ('B07G8W7FR8', 'Avento-White'),        # £490
    ('B07G8WNCK3', 'Avento-Blue'),         # £210
    ('B0C42LHKQ8', 'AVENTO-BLK-Red'),     # £210
]

# Exact match campaign — high-intent, higher bids
cname = f'SP_Exact_Avento_Growth_{TIMESTAMP}'
agname = 'Avento_Exact_AG'
rows.append(make_campaign_row(cname, 40, 'Manual'))
rows.append(make_ad_group_row(cname, agname, 0.65))
for asin, sku in avento_children:
    rows.append(make_product_ad_row(cname, agname, sku))
for kw in ['polarized sports sunglasses', 'running sunglasses',
           'cycling sunglasses men', 'sport sunglasses uv400',
           'polarized sunglasses for men', 'sports sunglasses for running']:
    rows.append(make_keyword_row(cname, agname, kw, 'exact', 0.65))

# ASIN targeting campaign — steal competitor traffic
cname2 = f'SP_ASIN_Avento_Conquest_{TIMESTAMP}'
agname2 = 'Avento_ASIN_AG'
rows.append(make_campaign_row(cname2, 25, 'Manual'))
rows.append(make_ad_group_row(cname2, agname2, 0.55))
for asin, sku in avento_children:
    rows.append(make_product_ad_row(cname2, agname2, sku))
# Product targeting — competitor ASINs (top UK sports sunglasses)
# Using own ASINs for cross-sell within the Avento range
for target_asin in ['B07G8WDT6H', 'B07G8SL62W', 'B0C2P48NCR', 'B07G8W7FR8']:
    pt_row = {h: '' for h in SP_HEADERS}
    pt_row['Product'] = 'Sponsored Products'
    pt_row['Entity'] = 'Product Targeting'
    pt_row['Operation'] = 'Create'
    pt_row['Campaign ID'] = cname2
    pt_row['Ad Group ID'] = agname2
    pt_row['State'] = 'enabled'
    pt_row['Bid'] = 0.55
    pt_row['Product Targeting Expression'] = f'asin="{target_asin}"'
    rows.append(pt_row)


# ═══════════════════════════════════════════════════════════════
# 2. VERANO — SCALE UP (21.0% TACOS, only £88 spend over 5W!)
#    Extremely efficient but starved. Create robust campaigns.
# ═══════════════════════════════════════════════════════════════

verano_children = [
    ('B07CNKVWQP', '9L-KQGW-DL1C'),      # £180 5W, top child
    ('B07CNSYJKD', 'QT-XAFB-5WKB'),      # £60
    ('B07CNYLXCC', '4L-T4SW-6S0T'),       # £91
    ('B07CNV788S', 'Y8-P4ZL-95RW'),       # £90
    ('B07CNV8S82', 'DT-7LPG-FVTB'),      # £0 — needs visibility
    ('B07CP3HSYD', 'F5-YYN7-BXR6'),      # £0 — needs visibility
]

# Manual broad + exact campaign
cname = f'SP_Manual_Verano_Growth_{TIMESTAMP}'
agname = 'Verano_Growth_AG'
rows.append(make_campaign_row(cname, 20, 'Manual'))
rows.append(make_ad_group_row(cname, agname, 0.50))
for asin, sku in verano_children:
    rows.append(make_product_ad_row(cname, agname, sku))
for kw in ['polarized sports sunglasses', 'anti slip sunglasses',
           'sunglasses men sports', 'lightweight sunglasses men',
           'running sunglasses uv400']:
    rows.append(make_keyword_row(cname, agname, kw, 'broad', 0.50))
for kw in ['polarized sports sunglasses', 'anti slip sunglasses']:
    rows.append(make_keyword_row(cname, agname, kw, 'exact', 0.55))


# ═══════════════════════════════════════════════════════════════
# 3. DYNAMIC — SCALE UP (11.7% TACOS, £25 total spend)
#    Best efficiency in entire UK account. Needs real campaigns.
# ═══════════════════════════════════════════════════════════════

dynamic_children = [
    ('B07CP26XD7', 'EC-AYZ3-HZH4'),      # £105, top child
    ('B07CP46YKD', '0P-KB7N-PEZ8'),       # £70
    ('B07CNNXJ4Y', '0Q-W0KH-ONYA'),      # £35
    ('B07CNSD47H', 'M1-25EO-C8P7'),      # £0
    ('B07CNZPNN9', 'ZH-EET1-OGHQ'),      # £0
]

# Manual campaign — moderate budget, broad KWs
cname = f'SP_Manual_Dynamic_Growth_{TIMESTAMP}'
agname = 'Dynamic_Growth_AG'
rows.append(make_campaign_row(cname, 15, 'Manual'))
rows.append(make_ad_group_row(cname, agname, 0.45))
for asin, sku in dynamic_children:
    rows.append(make_product_ad_row(cname, agname, sku))
for kw in ['polarized sports sunglasses', 'sunglasses men uv400',
           'sports sunglasses cycling', 'lightweight sport sunglasses']:
    rows.append(make_keyword_row(cname, agname, kw, 'broad', 0.45))
for kw in ['polarized sports sunglasses']:
    rows.append(make_keyword_row(cname, agname, kw, 'exact', 0.50))


# ═══════════════════════════════════════════════════════════════
# 4. VENTURA — NEW LAUNCH (6.9% TACOS, £7 total spend, £100 sales)
#    Nearly zero ad spend with great TACOS. High potential.
# ═══════════════════════════════════════════════════════════════

ventura_children = [
    ('B0CSYD3DWY', 'VT-BLK-R-Red 5'),    # £50
    ('B0CSYT7G9V', 'VT-BLK-R-Grey 5'),   # £50
    ('B0CSY8MBW8', 'VT-BLK-Y-Red 5'),    # £0
    ('B0CSYD66YR', 'VT-BLK-Y-Blue 5'),   # £0
    ('B0CSYHJ7MJ', 'VT-WHT-Blue 5'),     # £0
    ('B0CSYPVL3D', 'VT-WHT-Grey 5'),     # £0
]

# Auto campaign — discovery
cname = f'SP_Auto_Ventura_Launch_{TIMESTAMP}'
agname = 'Ventura_Auto_AG'
rows.append(make_campaign_row(cname, 10, 'Auto'))
rows.append(make_ad_group_row(cname, agname, 0.45))
for asin, sku in ventura_children:
    rows.append(make_product_ad_row(cname, agname, sku))

# Manual campaign
cname = f'SP_Manual_Ventura_Launch_{TIMESTAMP}'
agname = 'Ventura_Manual_AG'
rows.append(make_campaign_row(cname, 10, 'Manual'))
rows.append(make_ad_group_row(cname, agname, 0.45))
for asin, sku in ventura_children:
    rows.append(make_product_ad_row(cname, agname, sku))
for kw in ['sports sunglasses anti fog', 'performance sunglasses men',
           'high performance sunglasses', 'sunglasses cycling anti fog']:
    rows.append(make_keyword_row(cname, agname, kw, 'broad', 0.45))


# ═══════════════════════════════════════════════════════════════
# 5. LASO-17 — NEW LAUNCH (13.8% TACOS, £9 spend, £69 sales)
#    Efficient, needs visibility. Light budget test.
# ═══════════════════════════════════════════════════════════════

laso_children = [
    ('B0DWMF64DJ', 'Laso-17 BLK-Red'),
    ('B0DWMFL3JX', 'Laso-17 BLK-Brown'),
    ('B0DWMFPXKR', 'Laso-17 BLK-Gold'),
    ('B0DWMG7Q7D', 'Laso-17 BLK-Grey'),
    ('B0DWMGBB96', 'Laso-17 BLK-Blue'),
]

cname = f'SP_Auto_Laso17_Launch_{TIMESTAMP}'
agname = 'Laso17_Auto_AG'
rows.append(make_campaign_row(cname, 8, 'Auto'))
rows.append(make_ad_group_row(cname, agname, 0.40))
for asin, sku in laso_children:
    rows.append(make_product_ad_row(cname, agname, sku))

cname = f'SP_Manual_Laso17_Launch_{TIMESTAMP}'
agname = 'Laso17_Manual_AG'
rows.append(make_campaign_row(cname, 8, 'Manual'))
rows.append(make_ad_group_row(cname, agname, 0.40))
for asin, sku in laso_children:
    rows.append(make_product_ad_row(cname, agname, sku))
for kw in ['polarized sunglasses men', 'square sunglasses men',
           'lightweight sunglasses']:
    rows.append(make_keyword_row(cname, agname, kw, 'broad', 0.40))


# ═══════════════════════════════════════════════════════════════
# 6. WIRE STRAP (80Days 102) — NEW LAUNCH (12.2% TACOS, £17 spend)
#    Efficient strap product, currently under-advertised.
# ═══════════════════════════════════════════════════════════════

wire_strap_children = [
    ('B0G64L8VGX', 'Strap102-BLK/Grey'),   # £72, top child
    ('B0G653WYKH', 'Strap102-BLK/BLK'),    # £40
    ('B0G64Q4YRJ', 'Strap102-RED/BLK'),    # £20
    ('B0G64TMSXH', 'Strap102-OG/BLK'),     # £10
]

cname = f'SP_Auto_WireStrap_Launch_{TIMESTAMP}'
agname = 'WireStrap_Auto_AG'
rows.append(make_campaign_row(cname, 8, 'Auto'))
rows.append(make_ad_group_row(cname, agname, 0.33))  # Strap bid = £0.33
for asin, sku in wire_strap_children:
    rows.append(make_product_ad_row(cname, agname, sku))

cname = f'SP_Manual_WireStrap_Launch_{TIMESTAMP}'
agname = 'WireStrap_Manual_AG'
rows.append(make_campaign_row(cname, 8, 'Manual'))
rows.append(make_ad_group_row(cname, agname, 0.33))
for asin, sku in wire_strap_children:
    rows.append(make_product_ad_row(cname, agname, sku))
for kw in ['eyeglass strap', 'glasses strap', 'sunglass strap',
           'glasses holder', 'eyeglass retainer']:
    rows.append(make_keyword_row(cname, agname, kw, 'broad', 0.33))


# ═══════════════════════════════════════════════════════════════
# WRITE FILE
# ═══════════════════════════════════════════════════════════════

wb = openpyxl.Workbook()
write_sheet(wb, 'Sponsored Products Campaigns', SP_HEADERS, rows, SP_ID_COLS)
path = '/Users/koda/amazon-autopilot/clients/flux/bulk-output/UK_SP_GrowthRebalance_20260310.xlsx'
wb.save(path)

print(f'Created: {path}')
print(f'Total rows: {len(rows)}')
print()
print('=== NEW CAMPAIGNS CREATED (Growth / Scale) ===')
campaigns = [r for r in rows if r['Entity'] == 'Campaign']
total_budget = sum(c['Daily Budget'] for c in campaigns)
print(f'{"Campaign":<55s} {"Budget":>8s} {"Type":>8s}')
print('-' * 75)
for c in campaigns:
    print(f'{c["Campaign Name"]:<55s} £{c["Daily Budget"]:>5}/day  {c["Targeting Type"]:>8s}')
print(f'{"TOTAL DAILY BUDGET":<55s} £{total_budget:>5}/day')
print()
print('=== PENDING — NEED CAMPAIGN IDs FROM UK BULK DOWNLOAD ===')
print('PAUSE: 80Days Pilot campaigns      — 69.6% TACOS, W5 96.7%, losing £85/wk')
print('PAUSE: 80Days Oval campaigns        — 101.6% TACOS, pure loss')
print('PAUSE: 80Days Round campaigns       — 50.3% TACOS, zero W5 sales')
print('REDUCE: Nylon Strap bid -20%        — 34.7% TACOS, slightly over 30% target')
print('REDUCE: Sportech bid -15%           — 40.7% TACOS (but W5 improving)')
print()
print('>>> Ask Eric to download UK bulk xlsx so we can create pause/reduce file')
