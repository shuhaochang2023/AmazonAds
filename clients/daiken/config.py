from datetime import date

CLIENT_NAME   = "DAIKEN"
MARKET        = "US"
CURRENCY      = "$"
LOCALE        = "en-US"
TACOS_TARGET  = 70
REPORT_PERIOD = "Feb–Mar 2026"

WEEK_RANGES = {
    "W1": (date(2026,2,1),  date(2026,2,7)),
    "W2": (date(2026,2,8),  date(2026,2,14)),
    "W3": (date(2026,2,15), date(2026,2,21)),
    "W4": (date(2026,2,22), date(2026,2,28)),
    "W5": (date(2026,3,1),  date(2026,3,7)),
    # 每週加一行，例如：
    # "W6": (date(2026,3,8),  date(2026,3,14)),
}
W_LABELS = {
    "W1":"Feb 1–7", "W2":"Feb 8–14",
    "W3":"Feb 15–21", "W4":"Feb 22–28",
    "W5":"Mar 1–7",
    # "W6":"Mar 8–14",
}
FROZEN_WEEKS = ["W1","W2","W3","W4"]  # 這幾週不要動

# GitHub 部署設定
GITHUB_REPO   = "shuhaochang2023/AmazonAds"
DEPLOY_PATH   = "daiken/index.html"
EXCEL_NAME    = f"20260307_DAIKEN_US_{REPORT_PERIOD.replace('–','-')}.xlsx"
