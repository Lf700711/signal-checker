import unittest
from signal_checker.market import YahooProvider


class FakeDF:
    empty = True


class FakeTicker:
    def __init__(self, s): pass
    def history(self, **kw): return FakeDF()


class FakeYF:
    Ticker = FakeTicker


class MarketGuard(unittest.TestCase):
    def test_empty_daily_is_error_not_holiday(self):
        p = YahooProvider.__new__(YahooProvider)
        p.yf = FakeYF
        from datetime import date
        import signal_checker.market as m
        m._time.sleep = lambda *_: None
        with self.assertRaises(RuntimeError):
            p.daily("BITX", date(2026, 10, 1))


if __name__ == "__main__":
    unittest.main()
