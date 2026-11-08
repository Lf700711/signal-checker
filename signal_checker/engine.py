"""核心規則引擎：只做計算，不碰網路與檔案，方便測試。

名詞：
- side "long"  = 買進（做多）；side "short" = 賣出（放空）
- extreme      = 進場日起的極端價。做多為最高價，放空為最低價
- stage        = 出場價所在階段
                 0 = 初始停損
                 1 = 已獲利達第一門檻，出場價移到成本價
                 2 = 已達移動出場門檻，出場價隨高點/低點移動
"""
from dataclasses import dataclass

EPS = 1e-9


@dataclass(frozen=True)
class Rule:
    stop_pct: float           # 停損幅度（0.10 = 10%）
    be_pct: float             # 獲利達此幅度，出場價移到成本價
    trail_trigger_pct: float  # 獲利達此幅度，啟動移動出場
    trail_pct: float          # 做多：高點回撤幅度；放空：低點回彈幅度


STAGE_LABELS = {0: "初始停損", 1: "成本價保本", 2: "移動出場"}


def check_entry(side, prev, today):
    """檢查進場條件。

    prev:  前一日 K 線 dict(open, high, low, close)
    today: 當日開盤至今 dict(open, high, low)
    進場價 = 前日最高價（做多）／前日最低價（放空）
    """
    if side == "long":
        c1 = prev["open"] > prev["close"]      # 前日收黑
        c2 = today["open"] <= prev["high"]     # 今開 <= 前高
        c3 = today["high"] > prev["high"]      # 盤中突破前高
        entry = prev["high"]
    elif side == "short":
        c1 = prev["close"] > prev["open"]      # 前日收紅
        c2 = today["open"] >= prev["low"]      # 今開 >= 前低
        c3 = today["low"] < prev["low"]        # 盤中跌破前低
        entry = prev["low"]
    else:
        raise ValueError(f"unknown side: {side}")
    return {"c1": c1, "c2": c2, "c3": c3, "signal": c1 and c2 and c3, "entry_price": entry}


def trigger_prices(side, entry, rule):
    """以進場價算出：停損價、保本觸發價、移動出場觸發價。"""
    if side == "long":
        return {
            "stop": entry * (1 - rule.stop_pct),
            "be": entry * (1 + rule.be_pct),
            "trail": entry * (1 + rule.trail_trigger_pct),
        }
    return {
        "stop": entry * (1 + rule.stop_pct),
        "be": entry * (1 - rule.be_pct),
        "trail": entry * (1 - rule.trail_trigger_pct),
    }


def exit_level(side, entry, extreme, rule):
    """依進場價與目前極端價，算出出場價與階段。"""
    if side == "long":
        level = entry * (1 - rule.stop_pct)
        stage = 0
        if extreme >= entry * (1 + rule.be_pct) - EPS * entry:
            level = max(level, entry)
            stage = 1
        if extreme >= entry * (1 + rule.trail_trigger_pct) - EPS * entry:
            # 高點回撤；若低於成本價就以成本價出場
            level = max(level, entry, extreme * (1 - rule.trail_pct))
            stage = 2
        return level, stage

    level = entry * (1 + rule.stop_pct)
    stage = 0
    if extreme <= entry * (1 - rule.be_pct) + EPS * entry:
        level = min(level, entry)
        stage = 1
    if extreme <= entry * (1 - rule.trail_trigger_pct) + EPS * entry:
        # 低點回彈；若高於成本價就以成本價出場
        level = min(level, entry, extreme * (1 + rule.trail_pct))
        stage = 2
    return level, stage


def pnl_pct(side, entry, price):
    if side == "long":
        return (price - entry) / entry * 100
    return (entry - price) / entry * 100


def evaluate_position(side, entry_date, entry_price, bars, rule):
    """用「進場日起至前一日」的日K，推算目前出場價；並檢查是否已被觸發出場。

    bars: 依日期由舊到新排列的已完成日K，每筆 dict(date, open, high, low, close)。
          date 為 datetime.date。

    規則：
    - 進場日當天的高點(做多)/低點(放空)計入極端價，但進場日當天不判斷出場
      （因為無法知道高低點發生在進場前還是進場後）。
    - 進場日之後每一天，先用「前一天為止」的極端價算出場價，
      再看當天是否觸及；跳空越過出場價則以開盤價出場。
    - 同一天內先到高點再到停損的先後順序無法得知，以「前一天為止」的狀態判斷。
    """
    extreme = entry_price
    for b in bars:
        if b["date"] == entry_date:
            extreme = max(extreme, b["high"]) if side == "long" else min(extreme, b["low"])

    for b in bars:
        if b["date"] <= entry_date:
            continue
        level, stage = exit_level(side, entry_price, extreme, rule)
        if side == "long":
            hit = b["low"] <= level + EPS
            gap = b["open"] <= level
        else:
            hit = b["high"] >= level - EPS
            gap = b["open"] >= level
        if hit:
            exit_price = b["open"] if gap else level
            return {
                "closed": True,
                "exit_date": b["date"],
                "exit_price": exit_price,
                "pnl_pct": pnl_pct(side, entry_price, exit_price),
                "reason": STAGE_LABELS[stage],
                "stage": stage,
            }
        extreme = max(extreme, b["high"]) if side == "long" else min(extreme, b["low"])

    level, stage = exit_level(side, entry_price, extreme, rule)
    return {
        "closed": False,
        "extreme": extreme,
        "level": level,
        "stage": stage,
        "triggers": trigger_prices(side, entry_price, rule),
    }
