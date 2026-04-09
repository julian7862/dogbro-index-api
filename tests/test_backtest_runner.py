"""Unit tests for BacktestRunner."""

import os
import pytest
import tempfile
from datetime import datetime
from unittest.mock import Mock, patch

import pandas as pd

from src.backtesting.backtest_runner import BacktestRunner, BacktestBarResult
from src.backtesting.data_loader import HistoricalDataLoader


class TestBacktestRunner:
    """Tests for BacktestRunner class."""

    @pytest.fixture
    def mock_data_loader(self):
        """Create a mock data loader."""
        loader = Mock(spec=HistoricalDataLoader)

        # Mock TX data
        tx_data = pd.DataFrame({
            'datetime': pd.to_datetime([
                '2026-02-10 08:45',
                '2026-02-10 08:50',
                '2026-02-10 08:55',
            ]),
            'price': [32700.0, 32710.0, 32720.0]
        })
        loader.load_tx_bars.return_value = tx_data

        # Mock TXO data (multiple strikes per bar)
        txo_rows = []
        for dt in ['2026-02-10 08:45', '2026-02-10 08:50', '2026-02-10 08:55']:
            for strike in range(32300, 33100, 100):  # 8 strikes
                txo_rows.append({
                    'datetime': pd.to_datetime(dt),
                    'strike': strike,
                    'price': max(0, 32700 - strike + 200)  # Synthetic prices
                })
        txo_data = pd.DataFrame(txo_rows)
        loader.load_txo_bars.return_value = txo_data

        # Mock TAIEX close
        loader.load_taiex_close.return_value = 32650.0

        # Mock available dates
        loader.get_available_dates.return_value = ['2026-02-10']

        return loader

    def test_run_date_returns_results(self, mock_data_loader):
        """Test that run_date returns results for each bar."""
        runner = BacktestRunner(data_loader=mock_data_loader)
        results = runner.run_date('2026-02-10')

        assert len(results) == 3  # 3 bars
        assert all(isinstance(r, BacktestBarResult) for r in results)

    def test_run_date_calculates_civ(self, mock_data_loader):
        """Test that CIV is calculated for each bar."""
        runner = BacktestRunner(data_loader=mock_data_loader)
        results = runner.run_date('2026-02-10')

        # At least some bars should have CIV values
        civ_values = [r.civ for r in results if r.civ is not None]
        assert len(civ_values) > 0

    def test_run_date_uses_correct_dte(self, mock_data_loader):
        """Test that DTE is correctly calculated."""
        runner = BacktestRunner(data_loader=mock_data_loader)
        results = runner.run_date('2026-02-10')

        # February 2026 expiration is 2/23, so DTE should be 13
        assert all(r.dte == 13 for r in results)

    def test_run_date_missing_previous_close(self, mock_data_loader):
        """Test handling when previous close is not found."""
        mock_data_loader.load_taiex_close.return_value = None
        runner = BacktestRunner(data_loader=mock_data_loader)
        results = runner.run_date('2026-02-10')

        assert results == []

    def test_run_range_processes_all_dates(self, mock_data_loader):
        """Test that run_range processes all available dates."""
        mock_data_loader.get_available_dates.return_value = [
            '2026-02-10',
            '2026-02-11',
        ]

        runner = BacktestRunner(data_loader=mock_data_loader)
        summary = runner.run_range('2026-02-10', '2026-02-11')

        assert summary['days_processed'] == 2
        assert summary['total_bars'] == 6  # 3 bars * 2 days

    def test_run_range_filters_by_date(self, mock_data_loader):
        """Test that run_range only processes dates in range."""
        mock_data_loader.get_available_dates.return_value = [
            '2026-02-09',
            '2026-02-10',
            '2026-02-11',
        ]

        runner = BacktestRunner(data_loader=mock_data_loader)
        summary = runner.run_range('2026-02-10', '2026-02-10')

        assert summary['days_processed'] == 1

    def test_run_range_no_data(self, mock_data_loader):
        """Test run_range when no data in range."""
        mock_data_loader.get_available_dates.return_value = ['2026-03-01']

        runner = BacktestRunner(data_loader=mock_data_loader)
        summary = runner.run_range('2026-02-10', '2026-02-11')

        assert summary['days_processed'] == 0
        assert summary['total_bars'] == 0

    def test_bollinger_warmup_period(self, mock_data_loader):
        """Test that Bollinger indicators are None during warmup."""
        runner = BacktestRunner(data_loader=mock_data_loader)
        results = runner.run_date('2026-02-10')

        # First few bars should have None for Bollinger indicators
        # because we need 20+ bars of history
        first_result = results[0]
        assert first_result.civ_pb is None
        assert first_result.price_pb is None

    def test_reset_history(self, mock_data_loader):
        """Test that reset_history clears accumulated data."""
        runner = BacktestRunner(data_loader=mock_data_loader)

        # Run once to accumulate history
        runner.run_date('2026-02-10')
        assert len(runner._civ_history) > 0

        # Reset
        runner.reset_history()
        assert len(runner._civ_history) == 0
        assert len(runner._price_history) == 0

    def test_result_store_called(self, mock_data_loader):
        """Test that results are saved to store when provided."""
        mock_store = Mock()
        runner = BacktestRunner(
            data_loader=mock_data_loader,
            result_store=mock_store
        )

        runner.run_range('2026-02-10', '2026-02-10')

        mock_store.save_results.assert_called_once()
        call_args = mock_store.save_results.call_args
        assert call_args[0][0] == '2026-02-10'  # date
        assert len(call_args[0][1]) == 3  # results list
