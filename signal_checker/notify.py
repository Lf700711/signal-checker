"""組合通知內容並用 Gmail 寄出。

需要三個環境變數（在 GitHub 的 Secrets 設定）：
  GMAIL_USER          寄件的 Gmail 帳號
  GMAIL_APP_PASSWORD  Gmail「應用程式密碼」（16 碼，不是登入密碼）
  MAIL_TO             收件信箱（可以和寄件帳號相同）
"""
import html as _html
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from .config import SIDE_LABELS

WEEK = "一二三四五六日"


def _p(x):
    return f"{x:,.2f}"


def _pct(x):
    return f"{x:+.2f}%"


def _label(r):
    return f"{r['symbol']} {SIDE_LABELS[r['side']]}"


def _entry_lines(r):
    e = r["entry"]
    mark = lambda b: "✓" if b else "✗"  # noqa: E731
    long = r["side"] == "long"
    c1 = "前日收黑(開>收)" if long else "前日收紅(收>開)"
    c2 = "今開≤前高" if long else "今開≥前低"
    c3 = "盤中突破前高" if long else "盤中跌破前低"
    ref = "前日最高價" if long else "前日最低價"
    t = e["triggers"]
    lines = [
        f"  條件：{c1}{mark(e['c1'])}  {c2}{mark(e['c2'])}  {c3}{mark(e['c3'])}",
        f"  今日進場價（{ref}）：{_p(e['entry_price'])}  ｜ 目前價 {_p(r['today']['last'])}",
        f"  若進場：停損價 {_p(t['stop'])}；獲利達標價 保本 {_p(t['be'])}、移動出場啟動 {_p(t['trail'])}",
    ]
    return lines


def _pos_lines(r):
    p = r["position"]
    lines = [
        f"  進場 {p['entry_date']} @ {_p(p['entry_price'])}  ｜ 目前價 {_p(p['last'])}（{_pct(p['pnl_now'])}）",
        f"  今日出場價：{_p(p['level'])}（{p['stage_label']}）  ｜ 進場後{'最高' if r['side']=='long' else '最低'}價 {_p(p['extreme'])}",
        f"  保本啟動價 {_p(p['triggers']['be'])}；移動出場啟動價 {_p(p['triggers']['trail'])}",
    ]
    if p["hit_now"]:
        lines.append("  ⚠ 今日盤中價格已觸及出場價，請立即確認券商是否成交")
    return lines


def build(results, meta, positions):
    d = meta["ny_date"]
    wk = WEEK[__import__("datetime").date.fromisoformat(d).weekday()]
    signals = [r for r in results if r.get("entry", {}).get("signal")]
    holding = [r for r in results if r["has_position"]]
    events = [r for r in results if r.get("event")]
    idle = [r for r in results if not r["has_position"] and not r.get("entry", {}).get("signal")
            and "error" not in r]
    errors = [r for r in results if "error" in r]

    sub = f"[訊號] {d} 進場訊號 {len(signals)} 檔"
    if signals:
        sub += "：" + "、".join(_label(r) for r in signals)
    if events:
        sub += f"｜已出場 {len(events)}"
    if errors:
        sub += f"｜資料錯誤 {len(errors)}"

    L = [f"美股訊號檢查  {d}（週{wk}）  紐約時間 {meta['ny_time'][11:16]}"]
    if meta.get("data_time"):
        L.append(f"行情資料時間：紐約 {meta['data_time'][11:16]}"
                 + (f"（落後約 {meta['data_lag_min']:.0f} 分鐘，資料可能延遲）"
                    if meta.get("data_lag_min", 0) > 15 else ""))
    L.append(f"目前持有部位：{len(holding)} 個")
    L.append("")

    L.append(f"■ 進場訊號（{len(signals)}）— 需要你動作")
    if signals:
        for r in signals:
            L.append(f"● {_label(r)}  【達成進場條件】")
            L += _entry_lines(r)
        L.append("  成交後請到 GitHub 的 Record position 回報實際成交價，程式才會開始追蹤部位。")
    else:
        L.append("  無")
    L.append("")

    L.append(f"■ 部位狀態 = 有（{len(holding)}）")
    if holding:
        for r in holding:
            L.append(f"● {_label(r)}  【有部位】")
            L += _pos_lines(r)
    else:
        L.append("  無")
    L.append("")

    if events:
        L.append(f"■ 已自動出場（{len(events)}）— 依日K推算，請對照券商實際成交")
        for r in events:
            e = r["event"]
            L.append(f"● {_label(r)}  進場 {e['entry_date']} @ {_p(e['entry_price'])} → "
                     f"出場 {e['exit_date']} @ {_p(e['exit_price'])}（{e['exit_reason']}，{_pct(e['pnl_pct'])}）")
        L.append("  若實際成交價不同，可用 Record position 的 close 修正；已視為無部位，下方會重新檢查進場。")
        L.append("")

    L.append(f"■ 部位狀態 = 無，未達進場條件（{len(idle)}）— 以前日價格計算今日進場價")
    for r in idle:
        e = r["entry"]
        long = r["side"] == "long"
        L.append(f"● {_label(r)}  【無部位】")
        L += _entry_lines(r)
    if not idle:
        L.append("  無")

    if errors:
        L.append("")
        L.append(f"■ 資料錯誤（{len(errors)}）")
        for r in errors:
            L.append(f"● {_label(r)}：{r['error']}")

    L += ["", "※ 本程式只提供訊號與價位，不是投資建議；高槓桿 ETF 風險很高。",
          "※ 出場價請在券商設好停損單；本程式只在你手動執行時檢查一次，無法盯盤。"]
    text = "\n".join(L)
    htm = "<pre style=\"font-family:ui-monospace,Menlo,Consolas,monospace;font-size:13px;" \
          "line-height:1.5;white-space:pre-wrap\">" + _html.escape(text) + "</pre>"
    return sub, text, htm


def send(subject, text, html):
    user = os.environ.get("GMAIL_USER")
    pwd = os.environ.get("GMAIL_APP_PASSWORD")
    to = os.environ.get("MAIL_TO") or user
    if not user or not pwd:
        raise RuntimeError("缺少 GMAIL_USER 或 GMAIL_APP_PASSWORD，請到 GitHub Secrets 設定")
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to
    msg.attach(MIMEText(text, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as s:
        s.login(user, pwd)
        s.sendmail(user, [a.strip() for a in to.split(",")], msg.as_string())
