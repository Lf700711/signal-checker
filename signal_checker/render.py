"""把最新狀態產生成一個靜態網頁 docs/index.html（GitHub Pages 會自動發布）。"""
import html as _html
import os
from datetime import date

from . import store
from .config import KEYS, LONG_RULES, RULES, SHORT_RULES, SIDE_LABELS

DOCS_DIR = os.environ.get("SC_DOCS_DIR", "docs")
e = _html.escape


def _p(x):
    return f"{x:,.2f}"


def _row_cells(r, pos_now):
    """回傳 (狀態文字, css class, 欄位 list)。"""
    k = r["key"]
    long = r["side"] == "long"
    p = r.get("position")
    cur = pos_now.get(k)
    if cur:
        same = p and p["entry_price"] == cur["entry_price"] and p["entry_date"] == cur["entry_date"]
        if not same:  # 剛回報成交，價位等下次檢查才會更新
            return "有部位（待下次檢查更新價位）", "has", [
                cur["entry_date"], _p(cur["entry_price"]), "-", "-", "-", "-"]
    else:
        p = None
    if p:
        cls = "warn" if p["hit_now"] else "has"
        return ("有部位" + ("（⚠ 盤中已觸及出場價）" if p["hit_now"] else "")), cls, [
            p["entry_date"], _p(p["entry_price"]), _p(p["last"]) + f" ({p['pnl_now']:+.1f}%)",
            _p(p["level"]) + f"（{p['stage_label']}）", _p(p["extreme"]),
            f"保本 {_p(p['triggers']['be'])} / 移動 {_p(p['triggers']['trail'])}"]
    en = r.get("entry")
    if "error" in r or not en:
        return "資料錯誤", "err", ["-", "-", "-", "-", "-", e(r.get("error", ""))]
    mark = lambda b: "✓" if b else "✗"  # noqa: E731
    cond = f"{mark(en['c1'])}{mark(en['c2'])}{mark(en['c3'])}"
    if en["signal"]:
        return "進場訊號！", "sig", ["-", "-", _p(r["today"]["last"]),
                                   f"進場價 {_p(en['entry_price'])}", "-",
                                   f"停損 {_p(en['triggers']['stop'])} 條件 {cond}"]
    return "無部位", "none", ["-", "-", _p(r["today"]["last"]),
                             f"今日進場價 {_p(en['entry_price'])}", "-", f"條件 {cond}"]


def build_html(state, positions):
    meta = state.get("meta", {})
    results = {r["key"]: r for r in state.get("results", [])}
    pos_now = positions["open"]

    rows = []
    for sym, side in KEYS:
        k = store.key(sym, side)
        r = results.get(k, {"key": k, "symbol": sym, "side": side, "has_position": False,
                            "error": "尚未執行過檢查"})
        status, cls, cells = _row_cells(r, pos_now)
        tds = "".join(f"<td>{c}</td>" for c in cells)
        rows.append(f"<tr class='{cls}'><td><b>{e(sym)}</b><br><small>{e(SIDE_LABELS[side])}</small></td>"
                    f"<td>{e(status)}</td>{tds}</tr>")

    rule_rows = []
    for side, rules in (("long", LONG_RULES), ("short", SHORT_RULES)):
        for sym, ru in rules.items():
            tail = "回撤" if side == "long" else "回彈"
            rule_rows.append(
                f"<tr><td>{e(sym)}</td><td>{e(SIDE_LABELS[side])}</td><td>{ru.stop_pct*100:g}%</td>"
                f"<td>{ru.be_pct*100:g}%</td><td>{ru.trail_trigger_pct*100:g}%</td>"
                f"<td>{ru.trail_pct*100:g}%（{tail}）</td></tr>")

    hist = positions["closed"][-30:][::-1]
    hist_rows = "".join(
        f"<tr><td>{e(h['symbol'])} {e(SIDE_LABELS[h['side']])}</td><td>{e(h['entry_date'])}</td>"
        f"<td>{_p(h['entry_price'])}</td><td>{e(h['exit_date'])}</td><td>{_p(h['exit_price'])}</td>"
        f"<td>{h['pnl_pct']:+.2f}%</td><td>{e(h.get('exit_reason',''))}</td></tr>" for h in hist)
    if not hist_rows:
        hist_rows = "<tr><td colspan='7'>尚無已出場紀錄</td></tr>"

    run_info = (f"最近檢查：紐約時間 {e(meta.get('ny_time','-')[:16].replace('T',' '))}"
                f"（行情資料至 {e(meta.get('data_time','-')[11:16])}）") if meta else "尚未執行過檢查"

    return f"""<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>部位進出場訊號</title>
<style>
:root{{--bg:#fff;--fg:#1a1a1a;--mut:#666;--line:#ddd;--sig:#fff3cd;--has:#e7f3ff;--warn:#ffe0e0;--err:#eee}}
@media(prefers-color-scheme:dark){{:root{{--bg:#16181c;--fg:#e8e8e8;--mut:#9aa;--line:#333;--sig:#4a3f10;--has:#17324d;--warn:#5a2020;--err:#2a2a2a}}}}
body{{margin:0;padding:16px;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,-apple-system,"Noto Sans TC",sans-serif}}
h1{{font-size:20px;margin:0 0 4px}} h2{{font-size:16px;margin:28px 0 8px}}
.mut{{color:var(--mut);font-size:13px}}
.wrap{{overflow-x:auto}}
table{{border-collapse:collapse;width:100%;min-width:720px}}
th,td{{border:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top;font-size:13px}}
th{{background:var(--err)}}
tr.sig{{background:var(--sig)}} tr.has{{background:var(--has)}} tr.warn{{background:var(--warn)}} tr.err{{background:var(--err)}}
</style></head><body>
<h1>部位進出場訊號</h1>
<div class="mut">{run_info}　｜　目前持有部位 {len(pos_now)} 個</div>
<h2>目前狀態</h2>
<div class="wrap"><table>
<tr><th>標的/方向</th><th>狀態</th><th>進場日</th><th>進場價</th><th>目前價</th><th>出場價／今日進場價</th><th>進場後極端價</th><th>備註</th></tr>
{''.join(rows)}
</table></div>
<div class="mut">條件欄的三個符號依序為進場條件 1、2、3。黃色＝進場訊號；藍色＝有部位；紅色＝盤中已觸及出場價。</div>
<h2>已出場紀錄（最近 30 筆）</h2>
<div class="wrap"><table>
<tr><th>標的/方向</th><th>進場日</th><th>進場價</th><th>出場日</th><th>出場價</th><th>損益</th><th>出場原因</th></tr>
{hist_rows}
</table></div>
<h2>目前使用的出場規則</h2>
<div class="wrap"><table>
<tr><th>標的</th><th>方向</th><th>停損</th><th>獲利達此值→保本</th><th>獲利達此值以上→移動出場</th><th>移動幅度</th></tr>
{''.join(rule_rows)}
</table></div>
<p class="mut">本頁只提供訊號與價位，不是投資建議。高槓桿 ETF 風險很高，過去績效不代表未來。</p>
</body></html>"""


def write_site(state, positions):
    os.makedirs(DOCS_DIR, exist_ok=True)
    path = os.path.join(DOCS_DIR, "index.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(build_html(state, positions))
    # 讓 GitHub Pages 不要用 Jekyll 處理
    open(os.path.join(DOCS_DIR, ".nojekyll"), "a").close()
    return path
