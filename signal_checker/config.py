"""所有標的與出場規則都在這個檔案。要改參數只改這裡。

R(停損%, 保本觸發%, 移動出場觸發%, 回撤或回彈%)
  - 停損%         ：虧損達此幅度，停損出場
  - 保本觸發%     ：獲利達此幅度，出場價移到成本價
  - 移動出場觸發% ：獲利達此幅度以上，改用「高點回撤／低點回彈」出場價
  - 回撤或回彈%   ：做多＝從最高價回撤；放空＝從最低價回彈
"""
from .engine import Rule


def R(stop, be, trail_trigger, trail):
    return Rule(stop / 100, be / 100, trail_trigger / 100, trail / 100)


# 買進程式（做多）
LONG_RULES = {
    "BITX": R(10, 5, 10, 25),
    "ETHU": R(20, 5, 15, 5),
}

# 賣出程式（放空）
SHORT_RULES = {
    "SPXL": R(5, 10, 15, 5),
    "SPXU": R(5, 10, 10, 10),
    "TQQQ": R(5, 5, 15, 15),
    "SQQQ": R(5, 5, 25, 10),
    "SOXL": R(5, 5, 10, 5),
    "SOXS": R(5, 20, 25, 10),
    "FAZ": R(15, 5, 15, 5),
    "FAS": R(5, 15, 20, 5),
    "BITX": R(5, 5, 15, 10),
    "ETHU": R(5, 5, 20, 15),
}

RULES = {"long": LONG_RULES, "short": SHORT_RULES}
SIDE_LABELS = {"long": "買進(做多)", "short": "賣出(放空)"}

# 要檢查的 (標的, 方向) 清單；做多與放空各自獨立
KEYS = [(s, "long") for s in LONG_RULES] + [(s, "short") for s in SHORT_RULES]
SYMBOLS = sorted({s for s, _ in KEYS})

# 檢查時間窗（紐約時間）。排程可能延遲，所以給一段時間窗；一天只會成功執行一次。
RUN_START = (9, 35)
RUN_END = (11, 0)
NY_TZ = "America/New_York"
