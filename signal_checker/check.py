"""每日檢查主程式。

用法：
  python -m signal_checker.check              # 正式執行（有時間窗與每日一次的保護）
  python -m signal_checker.check --force      # 忽略時間窗與「今天已執行」的保護
  python -m signal_checker.check --dry-run    # 只印出結果，不寄信、不存檔
  python -m signal_checker.check --test-email # 只寄一封測試信，確認 Email 設定正確
"""
import argparse
import sys
from datetime import date, time, timedelta

from . import notify, render, store
from .config import KEYS, RULES, RUN_END, RUN_START, SYMBOLS
from .engine import check_entry, evaluate_position, pnl_pct, trigger_prices, STAGE_LABELS
from .market import YahooProvider, now_ny


def decide_run(now, state, force=False):
    """回傳 (要不要執行, 原因)。"""
    if force:
        return True, ""
    if now.weekday() >= 5:
        return False, "週末不檢查"
    t = now.time()
    if t < time(*RUN_START):
        return False, f"紐約時間 {t:%H:%M}，還沒到 {RUN_START[0]}:{RUN_START[1]:02d}"
    if t > time(*RUN_END):
        return False, f"紐約時間 {t:%H:%M}，已超過檢查時窗"
    if state.get("last_run_ny_date") == now.date().isoformat():
        return False, "今天已經檢查過了"
    return True, ""


def run(provider, now, positions):
    """核心流程（不碰檔案、不寄信）。會直接修改傳入的 positions（自動出場）。

    回傳 (results, meta)；休市（今天沒有盤中資料）時回傳 (None, meta)。
    """
    today = now.date()
    start = today - timedelta(days=25)
    for p in positions["open"].values():
        start = min(start, date.fromisoformat(p["entry_date"]) - timedelta(days=7))

    daily, intra, errors = {}, {}, {}
    for sym in SYMBOLS:
        try:
            intra[sym] = provider.intraday(sym, today)
            rows = provider.daily(sym, start)
            daily[sym] = [r for r in rows if r["date"] < today]   # 只取已收盤的日K
        except Exception as e:  # noqa: BLE001
            errors[sym] = f"{type(e).__name__}: {e}"

    have_today = [s for s in intra if intra[s] is not None]
    meta = {"ny_time": now.isoformat(timespec="seconds"), "ny_date": today.isoformat(),
            "errors": errors}
    if not have_today and not errors:
        return None, meta                       # 全部都沒有今天的盤中資料 = 休市

    last_times = [intra[s]["last_time"] for s in have_today]
    if last_times:
        meta["data_time"] = max(last_times).isoformat(timespec="seconds")
        lag = (now - max(last_times)).total_seconds() / 60
        meta["data_lag_min"] = round(lag, 1)

    results = []
    for sym, side in KEYS:
        k = store.key(sym, side)
        rule = RULES[side][sym]
        res = {"key": k, "symbol": sym, "side": side, "has_position": False}
        results.append(res)

        if sym in errors:
            res["error"] = f"資料抓取失敗：{errors[sym]}"
            continue
        bars, it = daily[sym], intra[sym]
        if not bars:
            res["error"] = "查無日K資料"
            continue
        if it is None:
            res["error"] = "查無今天的盤中資料"
            continue
        prev = bars[-1]
        res["prev"] = prev
        res["today"] = {"open": it["open"], "high": it["high"], "low": it["low"],
                        "last": it["last"]}

        pos = positions["open"].get(k)
        if pos:
            ev = evaluate_position(side, date.fromisoformat(pos["entry_date"]),
                                   pos["entry_price"], bars, rule)
            if ev["closed"]:
                rec = dict(pos)
                rec.update({
                    "exit_date": ev["exit_date"].isoformat(),
                    "exit_price": ev["exit_price"],
                    "pnl_pct": round(ev["pnl_pct"], 2),
                    "exit_reason": ev["reason"],
                    "auto": True,
                })
                positions["closed"].append(rec)
                del positions["open"][k]
                res["event"] = rec
                pos = None
            else:
                res["has_position"] = True
                entry = pos["entry_price"]
                last = it["last"]
                level = ev["level"]
                if side == "long":
                    hit_now = it["low"] <= level
                else:
                    hit_now = it["high"] >= level
                res["position"] = {
                    "entry_date": pos["entry_date"], "entry_price": entry,
                    "extreme": ev["extreme"], "level": level, "stage": ev["stage"],
                    "stage_label": STAGE_LABELS[ev["stage"]], "triggers": ev["triggers"],
                    "last": last, "pnl_now": pnl_pct(side, entry, last),
                    "hit_now": hit_now,
                }
                continue

        # 無部位 -> 檢查進場條件
        chk = check_entry(side, prev, it)
        entry = chk["entry_price"]
        res["entry"] = dict(chk)
        res["entry"]["triggers"] = trigger_prices(side, entry, rule)
    return results, meta


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--test-email", action="store_true")
    args = ap.parse_args(argv)

    if args.test_email:
        notify.send("[測試] 訊號檢查程式 Email 設定成功",
                    "這是一封測試信。收到代表 Email 設定正確。",
                    "<p>這是一封測試信。收到代表 Email 設定正確。</p>")
        print("測試信已寄出")
        return 0

    now = now_ny()
    positions = store.load_positions()
    state = store.load_state()

    ok, why = decide_run(now, state, args.force)
    if not ok:
        print(f"略過：{why}")
        return 0

    results, meta = run(YahooProvider(), now, positions)
    if results is None:
        print("今天沒有盤中資料（休市或資料源無回應），略過")
        return 0

    subject, text, html = notify.build(results, meta, positions)
    if args.dry_run:
        print(subject)
        print(text)
        return 0

    notify.send(subject, text, html)       # 先寄信；失敗就整個不存檔，下次重跑
    if len(meta["errors"]) >= len(SYMBOLS):
        print("所有標的資料都抓取失敗：已寄出錯誤通知，但不記錄為已執行，等備援排程重試")
        return 1
    state.update({
        "last_run_ny_date": now.date().isoformat(),
        "last_run_ny_time": meta["ny_time"],
        "meta": meta,
        "results": results,
    })
    store.save_positions(positions)
    store.save_state(state)
    render.write_site(store.load_state(), positions)
    print("完成：" + subject)
    return 0


if __name__ == "__main__":
    sys.exit(main())
