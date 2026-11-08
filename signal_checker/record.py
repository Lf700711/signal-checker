"""手動回報成交：開倉、平倉（修正）、刪除。

用法：
  python -m signal_checker.record open  BITX long  12.34 [--date 2026-11-09]
  python -m signal_checker.record close BITX long  13.10 [--date 2026-11-12]
  python -m signal_checker.record delete BITX long
open   ：登記新部位（該標的該方向必須目前沒有部位）
close  ：登記出場。若程式已自動標記出場，會用你給的實際成交價修正最近一筆紀錄
delete ：刪除目前部位（登記錯誤時用，不留紀錄）
"""
import argparse
import sys
from datetime import date

from . import render, store
from .config import KEYS
from .engine import pnl_pct
from .market import now_ny

VALID = set(KEYS)


def do_record(positions, action, symbol, side, price=None, on=None, today=None):
    """修改 positions 並回傳一句說明。出錯時丟 ValueError。"""
    symbol = symbol.upper()
    if (symbol, side) not in VALID:
        raise ValueError(f"不支援的標的/方向：{symbol} {side}")
    k = store.key(symbol, side)
    on = on or (today or now_ny().date()).isoformat()
    date.fromisoformat(on)  # 驗證日期格式

    if action == "open":
        if price is None or price <= 0:
            raise ValueError("開倉需要大於 0 的成交價")
        if k in positions["open"]:
            raise ValueError(f"{symbol} {side} 已有部位（進場 {positions['open'][k]['entry_date']}），"
                             "請先 close 或 delete")
        positions["open"][k] = {"symbol": symbol, "side": side, "entry_date": on,
                                "entry_price": float(price)}
        return f"已登記 {symbol} {side} 部位：{on} @ {price}"

    if action == "close":
        if price is None or price <= 0:
            raise ValueError("平倉需要大於 0 的成交價")
        if k in positions["open"]:
            pos = positions["open"].pop(k)
            rec = dict(pos)
            rec.update({"exit_date": on, "exit_price": float(price),
                        "pnl_pct": round(pnl_pct(side, pos["entry_price"], float(price)), 2),
                        "exit_reason": "手動回報", "auto": False})
            positions["closed"].append(rec)
            return f"已登記 {symbol} {side} 出場：{on} @ {price}（{rec['pnl_pct']:+.2f}%）"
        # 沒有目前部位：嘗試修正最近一筆已出場紀錄
        for rec in reversed(positions["closed"]):
            if rec["symbol"] == symbol and rec["side"] == side:
                rec["exit_price"] = float(price)
                rec["exit_date"] = on
                rec["pnl_pct"] = round(pnl_pct(side, rec["entry_price"], float(price)), 2)
                rec["exit_reason"] = "手動修正"
                rec["auto"] = False
                return f"已修正 {symbol} {side} 最近一筆出場：{on} @ {price}（{rec['pnl_pct']:+.2f}%）"
        raise ValueError(f"{symbol} {side} 目前沒有部位，也沒有可修正的出場紀錄")

    if action == "delete":
        if k not in positions["open"]:
            raise ValueError(f"{symbol} {side} 目前沒有部位")
        del positions["open"][k]
        return f"已刪除 {symbol} {side} 的目前部位"

    raise ValueError(f"未知動作：{action}")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["open", "close", "delete"])
    ap.add_argument("symbol")
    ap.add_argument("side", choices=["long", "short"])
    ap.add_argument("price", nargs="?", type=float)
    ap.add_argument("--date", default=None, help="YYYY-MM-DD，預設為紐約時間今天")
    args = ap.parse_args(argv)

    positions = store.load_positions()
    try:
        msg = do_record(positions, args.action, args.symbol, args.side, args.price, args.date)
    except ValueError as err:
        print(f"錯誤：{err}")
        return 1
    store.save_positions(positions)
    state = store.load_state()
    render.write_site(state, positions)
    print(msg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
