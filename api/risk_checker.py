"""
Pinch Risk Checker — 風險控制審核 Agent

在任何 API 操作執行前，先跑這個檢查。
違反 HARD 規則 → 擋住不執行
違反 SOFT 規則 → 警告

用法：
    from risk_checker import RiskChecker
    checker = RiskChecker()

    # 檢查 bid 調整
    result = checker.check_bid_change('DAIKEN', keyword='keyword_abc', current_bid=2.00, new_bid=2.60)
    if result.blocked:
        print(f"❌ 擋住: {result.reason}")

    # 檢查整批操作
    results = checker.check_action_plan(actions)
    results.print_report()
"""

import yaml
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class CheckResult:
    action: str
    blocked: bool = False
    warnings: List[str] = field(default_factory=list)
    reason: str = ""

    @property
    def passed(self):
        return not self.blocked and not self.warnings


@dataclass
class PlanReport:
    results: List[CheckResult] = field(default_factory=list)

    @property
    def blocked_count(self):
        return sum(1 for r in self.results if r.blocked)

    @property
    def warning_count(self):
        return sum(1 for r in self.results if r.warnings)

    @property
    def passed_count(self):
        return sum(1 for r in self.results if r.passed)

    @property
    def can_proceed(self):
        return self.blocked_count == 0

    def print_report(self):
        print("=" * 60)
        print("Pinch 風險檢查報告")
        print("=" * 60)

        if self.blocked_count:
            print(f"\n❌ 擋住: {self.blocked_count} 個操作")
            for r in self.results:
                if r.blocked:
                    print(f"   ❌ {r.action}: {r.reason}")

        if self.warning_count:
            print(f"\n⚠️  警告: {self.warning_count} 個操作")
            for r in self.results:
                for w in r.warnings:
                    print(f"   ⚠️  {r.action}: {w}")

        if self.passed_count:
            print(f"\n✅ 通過: {self.passed_count} 個操作")

        print()
        if self.can_proceed:
            print("✅ 全部通過，可以執行")
        else:
            print("❌ 有操作被擋住，請修正後重新檢查")
        print("=" * 60)


class RiskChecker:
    def __init__(self, rules_path=None):
        if rules_path is None:
            rules_path = Path(__file__).parent / 'risk_rules.yaml'
        with open(rules_path) as f:
            self.rules = yaml.safe_load(f)

    # ----------------------------------------------------------
    # Bid 檢查
    # ----------------------------------------------------------
    def check_bid_change(self, brand: str, keyword: str,
                         current_bid: float, new_bid: float,
                         daily_budget: float = None,
                         product_type: str = None) -> CheckResult:
        result = CheckResult(action=f"Bid change: {keyword} ${current_bid:.2f} → ${new_bid:.2f}")
        brand_upper = brand.upper()

        # 取得品牌規則
        bid_rules = self.rules.get('bid_caps', {}).get(brand_upper)
        if not bid_rules:
            result.warnings.append(f"找不到 {brand_upper} 的 bid 規則，使用預設")
            bid_rules = {'max_bid': 1.00, 'min_bid': 0.02,
                         'max_bid_increase_pct': 0, 'max_bid_decrease_pct': 30}

        # Flux 有 product type 區分
        if brand_upper == 'FLUX' and product_type:
            sub_rules = bid_rules.get(product_type.lower(), {})
            max_bid = sub_rules.get('max_bid', bid_rules.get('max_bid', 1.00))
            min_bid = sub_rules.get('min_bid', bid_rules.get('min_bid', 0.02))
        else:
            max_bid = bid_rules.get('max_bid', 1.00)
            min_bid = bid_rules.get('min_bid', 0.02)

        max_increase_pct = bid_rules.get('max_bid_increase_pct', 0)
        max_decrease_pct = bid_rules.get('max_bid_decrease_pct', 30)

        # HARD: 超過 max bid
        if new_bid > max_bid:
            result.blocked = True
            result.reason = f"Bid ${new_bid:.2f} 超過 {brand_upper} 上限 ${max_bid:.2f}"
            return result

        # HARD: 低於 min bid
        if new_bid < min_bid:
            result.blocked = True
            result.reason = f"Bid ${new_bid:.2f} 低於最低 ${min_bid:.2f}"
            return result

        # HARD: Bid 超過 daily budget
        budget_rules = self.rules.get('budget_rules', {})
        if daily_budget and budget_rules.get('bid_cannot_exceed_budget') and new_bid > daily_budget:
            result.blocked = True
            result.reason = f"Bid ${new_bid:.2f} 超過 Daily Budget ${daily_budget:.2f}"
            return result

        # HARD: 單次調整幅度
        if current_bid > 0:
            change_pct = abs(new_bid - current_bid) / current_bid * 100
            if new_bid > current_bid:
                result.blocked = True
                result.reason = (f"硬性規則：永遠不提高 bid "
                                 f"(${current_bid:.2f} → ${new_bid:.2f})")
                return result
            if new_bid < current_bid and change_pct > max_decrease_pct:
                result.blocked = True
                result.reason = (f"降 bid 幅度 {change_pct:.0f}% 超過上限 {max_decrease_pct}% "
                                 f"(${current_bid:.2f} → ${new_bid:.2f})")
                return result

        return result

    # ----------------------------------------------------------
    # 暫停檢查
    # ----------------------------------------------------------
    def check_pause(self, brand: str, target: str,
                    acos: float, spend: float) -> CheckResult:
        result = CheckResult(action=f"Pause: {target} (ACOS={acos:.0f}%, Spend=${spend:.2f})")
        brand_upper = brand.upper()

        pause_rules = self.rules.get('pause_rules', {}).get(brand_upper)
        if not pause_rules:
            result.warnings.append(f"找不到 {brand_upper} 的暫停規則")
            return result

        acos_threshold = pause_rules.get('pause_acos_threshold', 999)
        spend_threshold = pause_rules.get('pause_spend_threshold', 0)

        if acos < acos_threshold:
            result.blocked = True
            result.reason = f"ACOS {acos:.0f}% 未達暫停線 {acos_threshold}%，不應暫停"
            return result

        if spend < spend_threshold:
            result.blocked = True
            result.reason = f"Spend ${spend:.2f} 未達門檻 ${spend_threshold:.2f}，不應暫停"
            return result

        return result

    # ----------------------------------------------------------
    # Budget 檢查
    # ----------------------------------------------------------
    def check_budget_change(self, campaign: str,
                            current_budget: float, new_budget: float) -> CheckResult:
        result = CheckResult(action=f"Budget change: {campaign} ${current_budget:.2f} → ${new_budget:.2f}")
        budget_rules = self.rules.get('budget_rules', {})

        min_budget = budget_rules.get('min_daily_budget', 1.00)
        max_increase_pct = budget_rules.get('max_budget_increase_pct', 0)

        if new_budget < min_budget:
            result.blocked = True
            result.reason = f"Budget ${new_budget:.2f} 低於最低 ${min_budget:.2f}"
            return result

        if current_budget > 0 and new_budget > current_budget:
            result.blocked = True
            result.reason = (f"硬性規則：永遠不提高 budget "
                             f"(${current_budget:.2f} → ${new_budget:.2f})")
            return result

        return result

    # ----------------------------------------------------------
    # 禁止操作檢查
    # ----------------------------------------------------------
    def check_forbidden(self, action_type: str) -> CheckResult:
        result = CheckResult(action=f"Action: {action_type}")
        never_do = self.rules.get('never_do', [])

        if action_type in never_do:
            result.blocked = True
            result.reason = f"'{action_type}' 在禁止清單中，絕對不能執行"

        return result

    # ----------------------------------------------------------
    # 批量限制檢查
    # ----------------------------------------------------------
    def check_batch_size(self, bid_changes: int = 0,
                         pauses: int = 0,
                         campaigns_created: int = 0) -> CheckResult:
        result = CheckResult(action=f"Batch: {bid_changes} bid changes, {pauses} pauses, {campaigns_created} new campaigns")
        limits = self.rules.get('batch_limits', {})

        if bid_changes > limits.get('max_bid_changes_per_run', 200):
            result.blocked = True
            result.reason = f"Bid 變更 {bid_changes} 個超過上限 {limits['max_bid_changes_per_run']}"
            return result

        if pauses > limits.get('max_pauses_per_run', 50):
            result.blocked = True
            result.reason = f"暫停 {pauses} 個超過上限 {limits['max_pauses_per_run']}"
            return result

        if campaigns_created > limits.get('max_campaigns_created_per_run', 20):
            result.blocked = True
            result.reason = f"新建 {campaigns_created} 個 campaign 超過上限 {limits['max_campaigns_created_per_run']}"
            return result

        return result

    # ----------------------------------------------------------
    # 整批 Action Plan 檢查
    # ----------------------------------------------------------
    def check_action_plan(self, actions: list) -> PlanReport:
        """
        actions = [
            {'type': 'bid_change', 'brand': 'DAIKEN', 'keyword': 'xxx', 'current_bid': 2.0, 'new_bid': 2.3},
            {'type': 'pause', 'brand': 'DAIKEN', 'target': 'xxx', 'acos': 90, 'spend': 15},
            {'type': 'budget_change', 'campaign': 'xxx', 'current_budget': 10, 'new_budget': 20},
        ]
        """
        report = PlanReport()

        bid_changes = sum(1 for a in actions if a['type'] == 'bid_change')
        pauses = sum(1 for a in actions if a['type'] == 'pause')
        creates = sum(1 for a in actions if a['type'] == 'create_campaign')

        # 先檢查批量限制
        batch_result = self.check_batch_size(bid_changes, pauses, creates)
        if batch_result.blocked:
            report.results.append(batch_result)
            return report

        # 逐一檢查每個操作
        for action in actions:
            t = action['type']

            # 檢查是否在禁止清單
            forbidden = self.check_forbidden(t)
            if forbidden.blocked:
                report.results.append(forbidden)
                continue

            if t == 'bid_change':
                result = self.check_bid_change(
                    brand=action['brand'],
                    keyword=action.get('keyword', 'unknown'),
                    current_bid=action['current_bid'],
                    new_bid=action['new_bid'],
                    daily_budget=action.get('daily_budget'),
                    product_type=action.get('product_type'),
                )
            elif t == 'pause':
                result = self.check_pause(
                    brand=action['brand'],
                    target=action.get('target', 'unknown'),
                    acos=action['acos'],
                    spend=action['spend'],
                )
            elif t == 'budget_change':
                result = self.check_budget_change(
                    campaign=action.get('campaign', 'unknown'),
                    current_budget=action['current_budget'],
                    new_budget=action['new_budget'],
                )
            else:
                result = CheckResult(action=f"{t}", warnings=[f"未知操作類型: {t}"])

            report.results.append(result)

        return report


# ----------------------------------------------------------
# 直接執行測試
# ----------------------------------------------------------
if __name__ == '__main__':
    checker = RiskChecker()

    print("測試 DAIKEN bid 檢查：\n")

    # 測試 1: 正常調整
    r = checker.check_bid_change('DAIKEN', 'keyword_1', current_bid=2.00, new_bid=2.20)
    print(f"  $2.00 → $2.20: {'✅ 通過' if r.passed else '❌ ' + r.reason}")

    # 測試 2: 超過上限
    r = checker.check_bid_change('DAIKEN', 'keyword_2', current_bid=2.00, new_bid=3.00)
    print(f"  $2.00 → $3.00: {'✅ 通過' if r.passed else '❌ ' + r.reason}")

    # 測試 3: 漲幅太大
    r = checker.check_bid_change('DAIKEN', 'keyword_3', current_bid=1.50, new_bid=2.00)
    print(f"  $1.50 → $2.00: {'✅ 通過' if r.passed else '❌ ' + r.reason}")

    # 測試 4: Bid 超過 budget
    r = checker.check_bid_change('DAIKEN', 'keyword_4', current_bid=2.00, new_bid=2.20, daily_budget=2.00)
    print(f"  $2.00 → $2.20 (budget=$2): {'✅ 通過' if r.passed else '❌ ' + r.reason}")

    # 測試 5: 禁止操作
    r = checker.check_forbidden('add_negative_keywords')
    print(f"\n  加 Negative Keywords: {'✅ 通過' if r.passed else '❌ ' + r.reason}")

    # 測試 6: 整批 Action Plan
    print("\n\n測試整批 Action Plan：\n")
    actions = [
        {'type': 'bid_change', 'brand': 'DAIKEN', 'keyword': 'laser pen', 'current_bid': 2.00, 'new_bid': 2.20},
        {'type': 'bid_change', 'brand': 'DAIKEN', 'keyword': 'red laser', 'current_bid': 2.00, 'new_bid': 3.50},
        {'type': 'pause', 'brand': 'DAIKEN', 'target': 'blue laser', 'acos': 90, 'spend': 15},
        {'type': 'pause', 'brand': 'DAIKEN', 'target': 'green laser', 'acos': 50, 'spend': 3},
        {'type': 'budget_change', 'campaign': 'SP-DAIKEN-Auto', 'current_budget': 10, 'new_budget': 20},
        {'type': 'add_negative_keywords', 'brand': 'DAIKEN'},
    ]
    report = checker.check_action_plan(actions)
    report.print_report()
