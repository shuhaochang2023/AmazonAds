#!/usr/bin/env python3
"""Amazon 銷售報告自動化系統 — 讀取 CSV、彙整計算、生成 HTML 分析報告。"""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

# ---------- 路徑設定 ----------
BASE_DIR = Path(__file__).resolve().parent.parent
INPUT_DIR = BASE_DIR / "reports" / "input" / "daiken"
OUTPUT_DIR = BASE_DIR / "output" / "daiken"


# ---------- 工具函式 ----------
def parse_pct(value: str) -> float | None:
    """解析百分比字串，例如 '316.25 %' → 316.25，支援含逗號的負數。"""
    if not value or not value.strip():
        return None
    cleaned = value.replace("%", "").replace(",", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_num(value: str) -> float:
    """解析數值字串，空值回傳 0。"""
    if not value or not value.strip():
        return 0.0
    cleaned = value.replace(",", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def parse_date(value: str) -> datetime | None:
    """解析 DD-MMM-YY 格式日期。"""
    try:
        return datetime.strptime(value.strip(), "%d-%b-%y")
    except ValueError:
        return None


# ---------- 資料讀取 ----------
def load_csv_files(input_dir: Path) -> list[dict]:
    """讀取目錄下所有 CSV，回傳合併後的列表。"""
    rows = []
    csv_files = sorted(input_dir.glob("*.csv"))
    if not csv_files:
        raise FileNotFoundError(f"在 {input_dir} 找不到任何 CSV 檔案")

    for filepath in csv_files:
        print(f"讀取: {filepath.name}")
        with open(filepath, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row)
    print(f"共讀取 {len(rows)} 筆原始資料\n")
    return rows


# ---------- 彙整計算 ----------
class AsinStats:
    """單一 ASIN 的彙整統計。"""

    def __init__(self):
        self.total_orders = 0
        self.total_units = 0
        self.total_sales = 0.0
        self.total_profits = 0.0
        self.total_ppc_cost = 0.0
        self.total_ppc_sales = 0.0
        self.total_refund_units = 0
        self.total_refund_balance = 0.0
        self.days = 0
        self.min_date = None
        self.max_date = None

    @property
    def acos(self) -> float | None:
        """ACOS = PPC 花費 / PPC 銷售額 × 100"""
        if self.total_ppc_sales <= 0:
            return None
        return (self.total_ppc_cost / self.total_ppc_sales) * 100

    @property
    def tacos(self) -> float | None:
        """TACOS = PPC 花費 / 總銷售額 × 100"""
        if self.total_sales <= 0:
            return None
        return (self.total_ppc_cost / self.total_sales) * 100

    @property
    def margin(self) -> float | None:
        """利潤率 = 利潤 / 銷售額 × 100"""
        if self.total_sales <= 0:
            return None
        return (self.total_profits / self.total_sales) * 100

    @property
    def avg_order_value(self) -> float | None:
        if self.total_orders <= 0:
            return None
        return self.total_sales / self.total_orders


def aggregate(rows: list[dict]) -> dict[str, AsinStats]:
    """將原始資料按 ASIN 彙整。跳過非產品列（如 Sponsored Brands）。"""
    stats: dict[str, AsinStats] = {}

    for row in rows:
        asin = row.get("ASIN", "").strip()
        if not asin or not asin.startswith("B"):
            continue

        if asin not in stats:
            stats[asin] = AsinStats()

        s = stats[asin]
        s.total_orders += int(parse_num(row.get("Orders", "")))
        s.total_units += int(parse_num(row.get("Units", "")))
        s.total_sales += parse_num(row.get("Sales", ""))
        s.total_profits += parse_num(row.get("Profits", ""))
        s.total_ppc_cost += parse_num(row.get("PPC Cost", ""))
        s.total_ppc_sales += parse_num(row.get("PPC Sales", ""))
        s.total_refund_units += int(parse_num(row.get("Refund Units", "")))
        s.total_refund_balance += parse_num(row.get("Refund Balance", ""))
        s.days += 1

        dt = parse_date(row.get("Date", ""))
        if dt:
            if s.min_date is None or dt < s.min_date:
                s.min_date = dt
            if s.max_date is None or dt > s.max_date:
                s.max_date = dt

    return stats


# ---------- 排名分析 ----------
def rank_asins(stats: dict[str, AsinStats]) -> dict:
    """找出表現最好與最差的 ASIN。"""
    asins_with_sales = {k: v for k, v in stats.items() if v.total_sales > 0}

    if not asins_with_sales:
        return {"best": {}, "worst": {}}

    best_sales = max(asins_with_sales, key=lambda k: asins_with_sales[k].total_sales)
    worst_sales = min(asins_with_sales, key=lambda k: asins_with_sales[k].total_sales)
    best_margin = max(asins_with_sales, key=lambda k: asins_with_sales[k].margin or -9999)
    worst_margin = min(asins_with_sales, key=lambda k: asins_with_sales[k].margin or 9999)

    asins_with_acos = {k: v for k, v in asins_with_sales.items() if v.acos is not None}
    best_acos = min(asins_with_acos, key=lambda k: asins_with_acos[k].acos) if asins_with_acos else None
    worst_acos = max(asins_with_acos, key=lambda k: asins_with_acos[k].acos) if asins_with_acos else None

    return {
        "best": {
            "銷售額最高": best_sales,
            "利潤率最高": best_margin,
            "ACOS 最低（最佳）": best_acos,
        },
        "worst": {
            "銷售額最低": worst_sales,
            "利潤率最低": worst_margin,
            "ACOS 最高（最差）": worst_acos,
        },
    }


# ---------- HTML 報告生成 ----------
def fmt(value: float | None, suffix: str = "", decimals: int = 2) -> str:
    if value is None:
        return "—"
    return f"{value:,.{decimals}f}{suffix}"


def generate_html(stats: dict[str, AsinStats], rankings: dict, output_path: Path):
    """生成繁體中文 HTML 分析報告。"""
    sorted_asins = sorted(stats.items(), key=lambda x: x[1].total_sales, reverse=True)

    # 全帳戶彙總
    total_sales = sum(s.total_sales for _, s in sorted_asins)
    total_orders = sum(s.total_orders for _, s in sorted_asins)
    total_profits = sum(s.total_profits for _, s in sorted_asins)
    total_ppc_cost = sum(s.total_ppc_cost for _, s in sorted_asins)
    total_ppc_sales = sum(s.total_ppc_sales for _, s in sorted_asins)
    overall_acos = (total_ppc_cost / total_ppc_sales * 100) if total_ppc_sales > 0 else None
    overall_tacos = (total_ppc_cost / total_sales * 100) if total_sales > 0 else None
    overall_margin = (total_profits / total_sales * 100) if total_sales > 0 else None

    # 日期範圍
    all_dates = [s.min_date for _, s in sorted_asins if s.min_date] + \
                [s.max_date for _, s in sorted_asins if s.max_date]
    date_range = ""
    if all_dates:
        date_range = f"{min(all_dates).strftime('%Y-%m-%d')} ~ {max(all_dates).strftime('%Y-%m-%d')}"

    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    def ranking_card(title: str, category: str, color: str) -> str:
        items = rankings.get(category, {})
        cards_html = ""
        for label, asin in items.items():
            if asin is None:
                continue
            s = stats[asin]
            cards_html += f"""
            <div class="ranking-item">
                <div class="ranking-label">{label}</div>
                <div class="ranking-asin">{asin}</div>
                <div class="ranking-detail">
                    銷售額 £{fmt(s.total_sales)} ｜ 利潤率 {fmt(s.margin, '%')} ｜ ACOS {fmt(s.acos, '%')}
                </div>
            </div>"""
        return f"""
        <div class="ranking-section ranking-{color}">
            <h3>{title}</h3>
            {cards_html}
        </div>"""

    # 表格行
    table_rows = ""
    for asin, s in sorted_asins:
        margin_class = ""
        if s.margin is not None:
            margin_class = "positive" if s.margin > 0 else "negative"
        profit_class = "positive" if s.total_profits > 0 else "negative"

        table_rows += f"""
        <tr>
            <td class="asin">{asin}</td>
            <td class="num">{s.total_orders:,}</td>
            <td class="num">{s.total_units:,}</td>
            <td class="num">£{fmt(s.total_sales)}</td>
            <td class="num {profit_class}">£{fmt(s.total_profits)}</td>
            <td class="num {margin_class}">{fmt(s.margin, '%')}</td>
            <td class="num">£{fmt(s.total_ppc_cost)}</td>
            <td class="num">{fmt(s.acos, '%')}</td>
            <td class="num">{fmt(s.tacos, '%')}</td>
            <td class="num">{s.total_refund_units}</td>
            <td class="num">{s.days}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Daiken Amazon 銷售分析報告</title>
<style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f0f2f5; color: #1a1a2e; line-height: 1.6; }}
    .container {{ max-width: 1200px; margin: 0 auto; padding: 24px; }}
    h1 {{ font-size: 1.8rem; margin-bottom: 4px; }}
    .subtitle {{ color: #64748b; margin-bottom: 24px; font-size: 0.9rem; }}

    .summary-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px; margin-bottom: 32px; }}
    .summary-card {{ background: #fff; border-radius: 12px; padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
    .summary-card .label {{ font-size: 0.8rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; }}
    .summary-card .value {{ font-size: 1.5rem; font-weight: 700; margin-top: 4px; }}

    .ranking-container {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 32px; }}
    .ranking-section {{ background: #fff; border-radius: 12px; padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
    .ranking-section h3 {{ margin-bottom: 12px; font-size: 1.1rem; }}
    .ranking-green h3 {{ color: #16a34a; }}
    .ranking-red h3 {{ color: #dc2626; }}
    .ranking-item {{ padding: 10px 0; border-bottom: 1px solid #f1f5f9; }}
    .ranking-item:last-child {{ border-bottom: none; }}
    .ranking-label {{ font-size: 0.8rem; color: #64748b; }}
    .ranking-asin {{ font-weight: 700; font-size: 1rem; font-family: monospace; }}
    .ranking-detail {{ font-size: 0.8rem; color: #475569; margin-top: 2px; }}

    table {{ width: 100%; border-collapse: collapse; background: #fff; border-radius: 12px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
    th {{ background: #1e293b; color: #fff; padding: 12px 10px; font-size: 0.8rem; text-align: left; white-space: nowrap; }}
    td {{ padding: 10px; border-bottom: 1px solid #f1f5f9; font-size: 0.85rem; }}
    tr:hover {{ background: #f8fafc; }}
    .asin {{ font-family: monospace; font-weight: 600; }}
    .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
    .positive {{ color: #16a34a; }}
    .negative {{ color: #dc2626; }}

    .footer {{ text-align: center; color: #94a3b8; font-size: 0.75rem; margin-top: 32px; }}

    @media (max-width: 768px) {{
        .ranking-container {{ grid-template-columns: 1fr; }}
        table {{ font-size: 0.75rem; }}
        td, th {{ padding: 6px 4px; }}
    }}
</style>
</head>
<body>
<div class="container">
    <h1>Daiken Amazon 銷售分析報告</h1>
    <div class="subtitle">資料期間：{date_range} ｜ 報告產生時間：{now}</div>

    <div class="summary-grid">
        <div class="summary-card">
            <div class="label">總銷售額</div>
            <div class="value">£{fmt(total_sales)}</div>
        </div>
        <div class="summary-card">
            <div class="label">總訂單數</div>
            <div class="value">{total_orders:,}</div>
        </div>
        <div class="summary-card">
            <div class="label">總利潤</div>
            <div class="value" style="color:{'#16a34a' if total_profits >= 0 else '#dc2626'}">£{fmt(total_profits)}</div>
        </div>
        <div class="summary-card">
            <div class="label">整體利潤率</div>
            <div class="value">{fmt(overall_margin, '%')}</div>
        </div>
        <div class="summary-card">
            <div class="label">PPC 總花費</div>
            <div class="value">£{fmt(total_ppc_cost)}</div>
        </div>
        <div class="summary-card">
            <div class="label">整體 ACOS</div>
            <div class="value">{fmt(overall_acos, '%')}</div>
        </div>
        <div class="summary-card">
            <div class="label">整體 TACOS</div>
            <div class="value">{fmt(overall_tacos, '%')}</div>
        </div>
        <div class="summary-card">
            <div class="label">ASIN 數量</div>
            <div class="value">{len(stats)}</div>
        </div>
    </div>

    <div class="ranking-container">
        {ranking_card("🏆 表現最佳", "best", "green")}
        {ranking_card("⚠️ 需要關注", "worst", "red")}
    </div>

    <h2 style="margin-bottom: 12px;">各 ASIN 詳細數據</h2>
    <div style="overflow-x: auto;">
    <table>
        <thead>
            <tr>
                <th>ASIN</th>
                <th>訂單數</th>
                <th>銷售件數</th>
                <th>銷售額</th>
                <th>利潤</th>
                <th>利潤率</th>
                <th>PPC 花費</th>
                <th>ACOS</th>
                <th>TACOS</th>
                <th>退款件數</th>
                <th>活躍天數</th>
            </tr>
        </thead>
        <tbody>
            {table_rows}
        </tbody>
    </table>
    </div>

    <div class="footer">Amazon Autopilot — 自動生成報告</div>
</div>
</body>
</html>"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    print(f"報告已儲存至: {output_path}")


# ---------- 主流程 ----------
def main():
    print("=" * 50)
    print("  Amazon 銷售報告自動化系統")
    print("=" * 50 + "\n")

    rows = load_csv_files(INPUT_DIR)
    stats = aggregate(rows)

    print(f"共彙整 {len(stats)} 個 ASIN\n")
    print(f"{'ASIN':<18} {'訂單':>6} {'銷售額':>10} {'利潤':>10} {'ACOS':>8} {'TACOS':>8}")
    print("-" * 66)
    for asin, s in sorted(stats.items(), key=lambda x: x[1].total_sales, reverse=True):
        print(f"{asin:<18} {s.total_orders:>6,} {s.total_sales:>10,.2f} {s.total_profits:>10,.2f} {fmt(s.acos, '%'):>8} {fmt(s.tacos, '%'):>8}")

    rankings = rank_asins(stats)

    print("\n🏆 表現最佳:")
    for label, asin in rankings["best"].items():
        if asin:
            print(f"  {label}: {asin}")
    print("\n⚠️  需要關注:")
    for label, asin in rankings["worst"].items():
        if asin:
            print(f"  {label}: {asin}")

    output_path = OUTPUT_DIR / f"daiken_report_{datetime.now().strftime('%Y%m%d')}.html"
    generate_html(stats, rankings, output_path)


if __name__ == "__main__":
    main()
