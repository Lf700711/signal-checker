"""行情資料：目前用 yfinance（免費、非官方，偶爾會失敗，所以有重試）。

想換資料來源（例如 Alpaca）時，只要寫一個有 daily() 與 intraday() 兩個方法的類別即可。
"""
import time as _time
from datetime import date, datetime
from zoneinfo import ZoneInfo

from .config import NY_TZ

NY = ZoneInfo(NY_TZ)


def _retry(fn, tries=3, wait=4):
    last = None
    for i in range(tries):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001 - 網路錯誤種類很多，統一重試
            last = e
            if i < tries - 1:
                _time.sleep(wait * (i + 1))
    raise last


class YahooProvider:
    def __init__(self):
        import yfinance as yf  # 延後匯入，測試時不需要安裝
        self.yf = yf

    def daily(self, symbol, start: date):
        """回傳日K list[dict(date, open, high, low, close)]，由舊到新。
        價格為「已還原分割、未還原股息」的實際價格。"""
        df = _retry(lambda: self.yf.Ticker(symbol).history(
            start=start.isoformat(), interval="1d", auto_adjust=False, actions=False))
        if df is None or df.empty:
            # yfinance 在被擋或網路失敗時不一定丟錯，只會回傳空表；這裡明確當成錯誤，
            # 避免把「資料源失敗」誤判成「今天休市」
            raise RuntimeError(f"{symbol} 日K資料是空的（資料源可能暫時失敗）")
        rows = []
        for idx, r in df.iterrows():
            if any(_isnan(r[c]) for c in ("Open", "High", "Low", "Close")):
                continue
            rows.append({
                "date": idx.date(),
                "open": float(r["Open"]), "high": float(r["High"]),
                "low": float(r["Low"]), "close": float(r["Close"]),
            })
        return rows

    def intraday(self, symbol, ny_date: date):
        """回傳 ny_date 當天正常盤開盤至今的彙總；當天沒有資料（休市）回傳 None。"""
        df = _retry(lambda: self.yf.Ticker(symbol).history(
            period="2d", interval="1m", prepost=False, auto_adjust=False, actions=False))
        if df is None or df.empty:
            return None
        df = df.copy()
        df.index = df.index.tz_convert(NY)
        df = df[[d == ny_date for d in df.index.date]]
        df = df.dropna(subset=["Open", "High", "Low", "Close"])
        if df.empty:
            return None
        return {
            "open": float(df["Open"].iloc[0]),
            "high": float(df["High"].max()),
            "low": float(df["Low"].min()),
            "last": float(df["Close"].iloc[-1]),
            "last_time": df.index[-1].to_pydatetime(),
            "bars": int(len(df)),
        }


def _isnan(x):
    return x != x


def now_ny() -> datetime:
    return datetime.now(NY)
