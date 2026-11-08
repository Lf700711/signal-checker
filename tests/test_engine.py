import unittest
from datetime import date

from signal_checker.engine import (
    check_entry, exit_level, evaluate_position, trigger_prices, pnl_pct,
)
from signal_checker.config import R, LONG_RULES, SHORT_RULES


def bar(d, o, h, l, c):
    return {"date": d, "open": o, "high": h, "low": l, "close": c}


class EntryTests(unittest.TestCase):
    def test_long_signal(self):
        prev = dict(open=10, high=10.5, low=9.5, close=9.8)   # 收黑
        today = dict(open=10.2, high=10.6, low=10.1)
        r = check_entry("long", prev, today)
        self.assertTrue(r["signal"])
        self.assertEqual(r["entry_price"], 10.5)

    def test_long_prev_up_candle_blocks(self):
        prev = dict(open=10, high=10.5, low=9.5, close=10.2)  # 收紅
        r = check_entry("long", prev, dict(open=10.2, high=10.6, low=10.1))
        self.assertFalse(r["c1"])
        self.assertFalse(r["signal"])

    def test_long_gap_up_open_blocks(self):
        prev = dict(open=10, high=10.5, low=9.5, close=9.8)
        r = check_entry("long", prev, dict(open=10.7, high=11, low=10.6))
        self.assertFalse(r["c2"])
        self.assertFalse(r["signal"])

    def test_long_equal_high_not_breakout(self):
        prev = dict(open=10, high=10.5, low=9.5, close=9.8)
        r = check_entry("long", prev, dict(open=10.2, high=10.5, low=10.1))
        self.assertFalse(r["c3"])

    def test_long_open_equal_prev_high_ok(self):
        prev = dict(open=10, high=10.5, low=9.5, close=9.8)
        r = check_entry("long", prev, dict(open=10.5, high=10.6, low=10.4))
        self.assertTrue(r["c2"])
        self.assertTrue(r["signal"])

    def test_short_signal(self):
        prev = dict(open=10, high=10.5, low=9.5, close=10.3)  # 收紅
        r = check_entry("short", prev, dict(open=9.8, high=9.9, low=9.4))
        self.assertTrue(r["signal"])
        self.assertEqual(r["entry_price"], 9.5)

    def test_short_gap_down_open_blocks(self):
        prev = dict(open=10, high=10.5, low=9.5, close=10.3)
        r = check_entry("short", prev, dict(open=9.3, high=9.4, low=9.0))
        self.assertFalse(r["c2"])
        self.assertFalse(r["signal"])

    def test_short_prev_down_candle_blocks(self):
        prev = dict(open=10, high=10.5, low=9.5, close=9.8)
        r = check_entry("short", prev, dict(open=9.8, high=9.9, low=9.4))
        self.assertFalse(r["c1"])


class LevelTests(unittest.TestCase):
    def test_bitx_long_stages(self):
        rule = LONG_RULES["BITX"]  # 停損10 保本5 移動10 回撤25
        entry = 100
        self.assertEqual(exit_level("long", entry, 100, rule), (90.0, 0))
        self.assertEqual(exit_level("long", entry, 104.9, rule)[1], 0)
        self.assertEqual(exit_level("long", entry, 105, rule), (100, 1))
        self.assertEqual(exit_level("long", entry, 109, rule), (100, 1))
        # 高點 110 -> 110*0.75=82.5 < 成本 -> 成本價
        self.assertEqual(exit_level("long", entry, 110, rule), (100, 2))
        # 高點 140 -> 105
        lvl, st = exit_level("long", entry, 140, rule)
        self.assertAlmostEqual(lvl, 105.0)
        self.assertEqual(st, 2)

    def test_ethu_long_trail(self):
        rule = LONG_RULES["ETHU"]  # 20, 5, 15, 5
        lvl, st = exit_level("long", 100, 130, rule)
        self.assertAlmostEqual(lvl, 123.5)
        self.assertEqual(st, 2)
        self.assertEqual(exit_level("long", 100, 114.9, rule), (100, 1))

    def test_short_stages(self):
        rule = SHORT_RULES["SPXL"]  # 5, 10, 15, 5
        self.assertAlmostEqual(exit_level("short", 100, 100, rule)[0], 105)
        self.assertEqual(exit_level("short", 100, 90, rule), (100, 1))
        # 低點 85 -> 85*1.05=89.25 < 成本 -> 89.25
        lvl, st = exit_level("short", 100, 85, rule)
        self.assertAlmostEqual(lvl, 89.25)
        self.assertEqual(st, 2)
        # 低點 70 -> 73.5
        self.assertAlmostEqual(exit_level("short", 100, 70, rule)[0], 73.5)

    def test_short_trail_never_above_cost(self):
        rule = SHORT_RULES["SQQQ"]  # 5, 5, 25, 10
        # 低點 75 -> 75*1.1=82.5
        self.assertAlmostEqual(exit_level("short", 100, 75, rule)[0], 82.5)
        # 回彈幅度大時不得高於成本價
        rule2 = R(5, 5, 10, 30)
        lvl, st = exit_level("short", 100, 90, rule2)
        self.assertEqual(lvl, 100)
        self.assertEqual(st, 2)

    def test_float_boundary(self):
        # 100 * 1.1 在浮點數可能是 110.00000000000001，邊界要仍視為達標
        rule = LONG_RULES["BITX"]
        self.assertEqual(exit_level("long", 100, 100 * 1.1, rule)[1], 2)
        self.assertEqual(exit_level("long", 3.3, 3.3 * 1.05, rule)[1], 1)

    def test_trigger_prices(self):
        t = trigger_prices("long", 100, LONG_RULES["BITX"])
        self.assertAlmostEqual(t["stop"], 90)
        self.assertAlmostEqual(t["be"], 105)
        self.assertAlmostEqual(t["trail"], 110)
        t = trigger_prices("short", 100, SHORT_RULES["FAZ"])
        self.assertAlmostEqual(t["stop"], 115)
        self.assertAlmostEqual(t["be"], 95)
        self.assertAlmostEqual(t["trail"], 85)

    def test_pnl(self):
        self.assertAlmostEqual(pnl_pct("long", 100, 110), 10)
        self.assertAlmostEqual(pnl_pct("short", 100, 90), 10)
        self.assertAlmostEqual(pnl_pct("short", 100, 105), -5)


class EvaluateTests(unittest.TestCase):
    rule = LONG_RULES["BITX"]
    d = [date(2026, 11, i) for i in range(2, 14)]

    def test_no_bars_after_entry(self):
        r = evaluate_position("long", self.d[0], 100, [], self.rule)
        self.assertFalse(r["closed"])
        self.assertEqual(r["level"], 90)

    def test_entry_day_high_counts_but_no_exit_that_day(self):
        bars = [bar(self.d[0], 99, 112, 80, 100)]  # 進場日低點 80 不判斷出場
        r = evaluate_position("long", self.d[0], 100, bars, self.rule)
        self.assertFalse(r["closed"])
        self.assertEqual(r["extreme"], 112)
        self.assertEqual(r["stage"], 2)
        self.assertEqual(r["level"], 100)

    def test_stop_loss_hit(self):
        bars = [bar(self.d[0], 100, 101, 99, 100),
                bar(self.d[1], 98, 99, 89, 90)]
        r = evaluate_position("long", self.d[0], 100, bars, self.rule)
        self.assertTrue(r["closed"])
        self.assertAlmostEqual(r["exit_price"], 90)
        self.assertAlmostEqual(r["pnl_pct"], -10)
        self.assertEqual(r["exit_date"], self.d[1])

    def test_gap_down_exits_at_open(self):
        bars = [bar(self.d[0], 100, 101, 99, 100),
                bar(self.d[1], 85, 88, 80, 82)]
        r = evaluate_position("long", self.d[0], 100, bars, self.rule)
        self.assertTrue(r["closed"])
        self.assertEqual(r["exit_price"], 85)

    def test_breakeven_then_exit_at_cost(self):
        bars = [bar(self.d[0], 100, 101, 99, 100),
                bar(self.d[1], 101, 106, 100.5, 105),   # 高點 106 -> 保本
                bar(self.d[2], 104, 105, 99.5, 100)]    # 跌破成本 100
        r = evaluate_position("long", self.d[0], 100, bars, self.rule)
        self.assertTrue(r["closed"])
        self.assertAlmostEqual(r["exit_price"], 100)
        self.assertEqual(r["reason"], "成本價保本")

    def test_same_day_high_does_not_raise_level_for_that_day(self):
        # d1 高點達 106，但出場價以「前一日為止」計算 -> 當天仍是 90 的停損
        bars = [bar(self.d[0], 100, 101, 99, 100),
                bar(self.d[1], 101, 106, 95, 100)]
        r = evaluate_position("long", self.d[0], 100, bars, self.rule)
        self.assertFalse(r["closed"])
        self.assertEqual(r["stage"], 1)
        self.assertEqual(r["level"], 100)

    def test_trailing_exit(self):
        bars = [bar(self.d[0], 100, 101, 99, 100),
                bar(self.d[1], 101, 140, 100, 138),
                bar(self.d[2], 138, 139, 104, 106)]  # 高點140 -> 105，跌到 104
        r = evaluate_position("long", self.d[0], 100, bars, self.rule)
        self.assertTrue(r["closed"])
        self.assertAlmostEqual(r["exit_price"], 105)
        self.assertEqual(r["reason"], "移動出場")
        self.assertAlmostEqual(r["pnl_pct"], 5)

    def test_short_stop_and_gap(self):
        rule = SHORT_RULES["TQQQ"]  # 5,5,15,15
        bars = [bar(self.d[0], 100, 100.5, 99, 99.5),
                bar(self.d[1], 106, 107, 105, 106)]   # 跳空越過 105 -> 開盤出場
        r = evaluate_position("short", self.d[0], 100, bars, rule)
        self.assertTrue(r["closed"])
        self.assertEqual(r["exit_price"], 106)
        self.assertAlmostEqual(r["pnl_pct"], -6)

    def test_short_trailing(self):
        rule = SHORT_RULES["SPXL"]  # 5,10,15,5
        bars = [bar(self.d[0], 100, 100.5, 99, 99.5),
                bar(self.d[1], 99, 99, 80, 82),         # 低點 80 -> 達15% -> 80*1.05=84
                bar(self.d[2], 82, 85, 81, 84)]         # 高點 85 >= 84 -> 84 出場
        r = evaluate_position("short", self.d[0], 100, bars, rule)
        self.assertTrue(r["closed"])
        self.assertAlmostEqual(r["exit_price"], 84)
        self.assertAlmostEqual(r["pnl_pct"], 16)


if __name__ == "__main__":
    unittest.main()
