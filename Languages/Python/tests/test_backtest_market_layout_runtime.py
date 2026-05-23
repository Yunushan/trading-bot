import os
import sys
import unittest
from pathlib import Path


PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6 import QtWidgets

    from app.gui.backtest import backtest_tab_market_runtime

    PYQT_AVAILABLE = True
    PYQT_UNAVAILABLE_REASON = ""
except Exception as exc:
    PYQT_AVAILABLE = False
    PYQT_UNAVAILABLE_REASON = str(exc)


@unittest.skipUnless(PYQT_AVAILABLE, f"PyQt6 unavailable: {PYQT_UNAVAILABLE_REASON}")
class BacktestMarketLayoutRuntimeTests(unittest.TestCase):
    def test_backtest_market_lists_are_height_bounded(self):
        _app = QtWidgets.QApplication.instance()
        if _app is None:
            _app = QtWidgets.QApplication([])

        class _DummyBacktestWindow:
            def _backtest_symbol_source_changed(self, *_args):
                return None

            def _refresh_backtest_symbols(self):
                return None

            def _backtest_store_symbols(self):
                return None

            def _backtest_store_intervals(self):
                return None

            def _create_override_group(self, _kind, _symbol_list, _interval_list):
                return QtWidgets.QGroupBox("Symbol / Interval Overrides")

        window = _DummyBacktestWindow()
        group = backtest_tab_market_runtime.build_backtest_market_group(window)

        self.assertEqual(group.sizePolicy().verticalPolicy(), QtWidgets.QSizePolicy.Policy.Maximum)
        self.assertEqual(
            window.backtest_symbol_list.minimumHeight(),
            backtest_tab_market_runtime.BACKTEST_MARKET_LIST_MIN_HEIGHT,
        )
        self.assertEqual(
            window.backtest_symbol_list.maximumHeight(),
            backtest_tab_market_runtime.BACKTEST_MARKET_LIST_MAX_HEIGHT,
        )
        self.assertEqual(
            window.backtest_interval_list.minimumHeight(),
            backtest_tab_market_runtime.BACKTEST_MARKET_LIST_MIN_HEIGHT,
        )
        self.assertEqual(
            window.backtest_interval_list.maximumHeight(),
            backtest_tab_market_runtime.BACKTEST_MARKET_LIST_MAX_HEIGHT,
        )


if __name__ == "__main__":
    unittest.main()
