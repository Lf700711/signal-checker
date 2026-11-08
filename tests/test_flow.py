import os
import tempfile
import unittest
from datetime import date, datetime
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")

_tmp = tempfile.mkdtemp()
os.environ["SC_DATA_DIR"] = os.path.join(_tmp, "data")
os.environ["SC_DOCS_DIR"] = os.path.join(_tmp, "docs")

from signal_checker import check, notify, record, render, store  # noqa: E402
from signal_checker.config import KEYS, SYMBOLS  # noqa: E402

TODAY = date(2026, 11, 9)          # 週一
NOW = datetime(2026, 11, 9, 9, 36, tzinfo=NY)


def bar(d, o, h, l, c):
    return {"date": d, "open": o, "high": h, "low": l, "close": c}


class FakeProvider:
    """每個標的前日都是黑K（開10收9.8、高10.5、低9.5），今日預設不突破。"""

    def __init__(self):
        self.daily_rows = {}
        self.intra = {}
        for s in SYMBOLS:
            self.daily_rows[s] = [bar(date(2026, 11, 5), 10, 10.4, 9.7, 10.1),
                                  bar(date(2026, 11, 6), 10, 10.5, 9.5, 9.8),
                                  bar(TODAY, 9.9, 9.9, 9.9, 9.9)]   # 今天未完成的日K，應被忽略
            self.intra[s] = {"open": 10.0, "high": 10.1, "low": 9.9, "last": 10.0,
                             "last_time": NOW.replace(minute=35), "bars": 6}

    def daily(self, symbol, start):
        return self.daily_rows[symbol]

    def intraday(self, symbol, d):
        return self.intra[symbol]


class FlowTests(unittest.TestCase):
    def setUp(self):
        self.p = FakeProvider()
        self.pos = {"open": {}, "closed": []}

    def res(self, results, sym, side):
        return next(r for r in results if r["symbol"] == sym and r["side"] == side)

    def test_covers_all_keys(self):
        results, _ = check.run(self.p, NOW, self.pos)
        self.assertEqual(len(results), 12)
        self.assertEqual({(r["symbol"], r["side"]) for r in results}, set(KEYS))

    def test_long_signal_uses_prev_high_and_ignores_today_partial_bar(self):
        self.p.intra["BITX"].update(high=10.6)       # 突破前高 10.5
        results, _ = check.run(self.p, NOW, self.pos)
        r = self.res(results, "BITX", "long")
        self.assertTrue(r["entry"]["signal"])
        self.assertEqual(r["entry"]["entry_price"], 10.5)
        self.assertEqual(r["prev"]["date"], date(2026, 11, 6))
        self.assertAlmostEqual(r["entry"]["triggers"]["stop"], 10.5 * 0.9)
        # 同一標的放空：前日黑K，不符合放空條件
        self.assertFalse(self.res(results, "BITX", "short")["entry"]["signal"])

    def test_short_signal(self):
        # 放空需要前日紅K
        self.p.daily_rows["SOXL"][1] = bar(date(2026, 11, 6), 9.5, 10.5, 9.5, 10.3)
        self.p.intra["SOXL"].update(open=9.8, low=9.4)
        results, _ = check.run(self.p, NOW, self.pos)
        r = self.res(results, "SOXL", "short")
        self.assertTrue(r["entry"]["signal"])
        self.assertEqual(r["entry"]["entry_price"], 9.5)

    def test_open_position_shows_levels_and_blocks_new_entry(self):
        self.p.intra["BITX"].update(high=10.6)
        self.pos["open"]["BITX:long"] = {"symbol": "BITX", "side": "long",
                                          "entry_date": "2026-11-05", "entry_price": 10.0}
        results, _ = check.run(self.p, NOW, self.pos)
        r = self.res(results, "BITX", "long")
        self.assertTrue(r["has_position"])
        self.assertNotIn("entry", r)                  # 有部位不檢查進場
        # 進場日 11/5 高點 10.4、11/6 高點 10.5 -> 最高 10.5 (5%) -> 保本 10.0
        self.assertAlmostEqual(r["position"]["extreme"], 10.5)
        self.assertEqual(r["position"]["stage"], 1)
        self.assertAlmostEqual(r["position"]["level"], 10.0)

    def test_auto_exit_then_recheck_entry_same_run(self):
        self.pos["open"]["BITX:long"] = {"symbol": "BITX", "side": "long",
                                          "entry_date": "2026-11-04", "entry_price": 11.0}
        # 11/5 低點 9.7 <= 停損 9.9 -> 11/5 出場（開盤 10 > 停損，所以以停損價出場）
        self.p.daily_rows["BITX"].insert(0, bar(date(2026, 11, 4), 11, 11, 10.8, 10.9))
        results, _ = check.run(self.p, NOW, self.pos)
        r = self.res(results, "BITX", "long")
        self.assertIn("event", r)
        self.assertFalse(r["has_position"])
        self.assertIn("entry", r)                     # 出場後立刻重新檢查進場
        self.assertEqual(self.pos["open"], {})
        self.assertEqual(len(self.pos["closed"]), 1)
        self.assertAlmostEqual(self.pos["closed"][0]["exit_price"], 9.9)
        self.assertAlmostEqual(self.pos["closed"][0]["pnl_pct"], -10.0)

    def test_market_closed_returns_none(self):
        for s in SYMBOLS:
            self.p.intra[s] = None
        results, meta = check.run(self.p, NOW, self.pos)
        self.assertIsNone(results)

    def test_one_symbol_error_does_not_break_others(self):
        orig = self.p.daily

        def bad(symbol, start):
            if symbol == "ETHU":
                raise RuntimeError("boom")
            return orig(symbol, start)
        self.p.daily = bad
        results, meta = check.run(self.p, NOW, self.pos)
        self.assertIn("error", self.res(results, "ETHU", "long"))
        self.assertIn("error", self.res(results, "ETHU", "short"))
        self.assertNotIn("error", self.res(results, "BITX", "long"))
        self.assertIn("ETHU", meta["errors"])

    def test_email_and_site_render(self):
        self.p.intra["BITX"].update(high=10.6)
        self.pos["open"]["TQQQ:short"] = {"symbol": "TQQQ", "side": "short",
                                           "entry_date": "2026-11-06", "entry_price": 10.0}
        results, meta = check.run(self.p, NOW, self.pos)
        subject, text, html = notify.build(results, meta, self.pos)
        self.assertIn("BITX", subject)
        self.assertIn("進場訊號", text)
        self.assertIn("部位狀態 = 有", text)
        self.assertIn("以前日價格計算今日進場價", text)
        self.assertIn("10.50", text)
        state = {"meta": meta, "results": results}
        page = render.build_html(state, self.pos)
        self.assertIn("BITX", page)
        self.assertIn("進場訊號！", page)
        self.assertIn("目前使用的出場規則", page)


class DecideTests(unittest.TestCase):
    def d(self, h, m, day=9):
        return datetime(2026, 11, day, h, m, tzinfo=NY)

    def test_window(self):
        self.assertFalse(check.decide_run(self.d(9, 30), {})[0])
        self.assertTrue(check.decide_run(self.d(9, 35), {})[0])
        self.assertTrue(check.decide_run(self.d(10, 59), {})[0])
        self.assertFalse(check.decide_run(self.d(11, 1), {})[0])

    def test_weekend_and_done_and_force(self):
        self.assertFalse(check.decide_run(self.d(9, 40, day=7), {})[0])   # 週六
        self.assertFalse(check.decide_run(self.d(9, 40), {"last_run_ny_date": "2026-11-09"})[0])
        self.assertTrue(check.decide_run(self.d(9, 40), {"last_run_ny_date": "2026-11-09"}, force=True)[0])


class RecordTests(unittest.TestCase):
    def test_open_close_delete(self):
        pos = {"open": {}, "closed": []}
        record.do_record(pos, "open", "bitx", "long", 10.0, "2026-11-09")
        self.assertIn("BITX:long", pos["open"])
        with self.assertRaises(ValueError):
            record.do_record(pos, "open", "BITX", "long", 10.0, "2026-11-09")
        # 買進與放空獨立
        record.do_record(pos, "open", "BITX", "short", 10.0, "2026-11-09")
        self.assertEqual(len(pos["open"]), 2)
        record.do_record(pos, "close", "BITX", "long", 11.0, "2026-11-10")
        self.assertAlmostEqual(pos["closed"][0]["pnl_pct"], 10.0)
        # 對已自動出場的紀錄做修正
        record.do_record(pos, "close", "BITX", "long", 10.5, "2026-11-10")
        self.assertAlmostEqual(pos["closed"][0]["pnl_pct"], 5.0)
        record.do_record(pos, "delete", "BITX", "short")
        self.assertEqual(pos["open"], {})

    def test_bad_input(self):
        pos = {"open": {}, "closed": []}
        with self.assertRaises(ValueError):
            record.do_record(pos, "open", "AAPL", "long", 10, "2026-11-09")
        with self.assertRaises(ValueError):
            record.do_record(pos, "open", "SPXL", "long", 10, "2026-11-09")   # SPXL 只有放空
        with self.assertRaises(ValueError):
            record.do_record(pos, "open", "BITX", "long", -1, "2026-11-09")
        with self.assertRaises(ValueError):
            record.do_record(pos, "open", "BITX", "long", 10, "11/09/2026")
        with self.assertRaises(ValueError):
            record.do_record(pos, "close", "BITX", "long", 10, "2026-11-09")


class StoreTests(unittest.TestCase):
    def test_roundtrip_with_dates(self):
        store.save_state({"x": {"d": date(2026, 11, 9)}})
        self.assertEqual(store.load_state()["x"]["d"], "2026-11-09")


if __name__ == "__main__":
    unittest.main()
