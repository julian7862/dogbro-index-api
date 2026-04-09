"""Unit tests for HistoricalDataLoader."""

import os
import pytest
import tempfile
from datetime import date

from src.backtesting.data_loader import HistoricalDataLoader


class TestHistoricalDataLoader:
    """Tests for HistoricalDataLoader class."""

    @pytest.fixture
    def temp_dirs(self):
        """Create temporary directories with test CSV files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tx_path = os.path.join(tmpdir, 'tx')
            txo_path = os.path.join(tmpdir, 'txo')
            taiex_path = os.path.join(tmpdir, 'taiex')
            os.makedirs(tx_path)
            os.makedirs(txo_path)
            os.makedirs(taiex_path)

            # Create TX CSV
            tx_csv = os.path.join(tx_path, 'tx_5min_kbar_2026_02_10.csv')
            with open(tx_csv, 'w') as f:
                f.write('datetime,price\n')
                f.write('2026-02-09 15:05,32605.0\n')
                f.write('2026-02-09 15:10,32580.0\n')
                f.write('2026-02-10 08:45,32700.0\n')

            # Create TXO CSV
            txo_csv = os.path.join(txo_path, '5min_kbar_2026_02_10.csv')
            with open(txo_csv, 'w') as f:
                f.write('datetime,strike,price\n')
                f.write('2026-02-10 08:45,32500,280.0\n')
                f.write('2026-02-10 08:45,32600,220.0\n')
                f.write('2026-02-10 08:45,32700,165.0\n')

            # Create TAIEX CSV (Big5 encoded with ROC year)
            taiex_csv = os.path.join(taiex_path, 'TAIEX_HIST_02.csv')
            content = '"115年02月 發行量加權股價指數歷史資料"\n'
            content += '"日期","開盤指數","最高指數","最低指數","收盤指數"\n'
            content += '"115/02/09","32,008.46","32,666.05","31,956.21","32,404.62"\n'
            content += '"115/02/10","32,439.71","33,072.97","32,439.71","33,072.97"\n'
            with open(taiex_csv, 'w', encoding='big5') as f:
                f.write(content)

            yield {
                'tx_path': tx_path,
                'txo_path': txo_path,
                'taiex_path': taiex_path,
            }

    def test_load_tx_bars(self, temp_dirs):
        """Test loading TX futures data."""
        loader = HistoricalDataLoader(**temp_dirs)
        df = loader.load_tx_bars('2026-02-10')

        assert not df.empty
        assert 'datetime' in df.columns
        assert 'price' in df.columns
        assert len(df) == 3
        assert df.iloc[0]['price'] == 32605.0

    def test_load_tx_bars_file_not_found(self, temp_dirs):
        """Test loading TX data when file doesn't exist."""
        loader = HistoricalDataLoader(**temp_dirs)
        df = loader.load_tx_bars('2026-01-01')

        assert df.empty
        assert list(df.columns) == ['datetime', 'price']

    def test_load_txo_bars(self, temp_dirs):
        """Test loading TXO options data."""
        loader = HistoricalDataLoader(**temp_dirs)
        df = loader.load_txo_bars('2026-02-10')

        assert not df.empty
        assert 'datetime' in df.columns
        assert 'strike' in df.columns
        assert 'price' in df.columns
        assert len(df) == 3
        assert set(df['strike'].unique()) == {32500, 32600, 32700}

    def test_load_txo_bars_file_not_found(self, temp_dirs):
        """Test loading TXO data when file doesn't exist."""
        loader = HistoricalDataLoader(**temp_dirs)
        df = loader.load_txo_bars('2026-01-01')

        assert df.empty
        assert list(df.columns) == ['datetime', 'strike', 'price']

    def test_load_taiex_close(self, temp_dirs):
        """Test loading TAIEX closing index."""
        loader = HistoricalDataLoader(**temp_dirs)
        close = loader.load_taiex_close('2026-02-09')

        assert close is not None
        assert close == 32404.62

    def test_load_taiex_close_date_not_found(self, temp_dirs):
        """Test loading TAIEX when date doesn't exist."""
        loader = HistoricalDataLoader(**temp_dirs)
        close = loader.load_taiex_close('2026-01-01')

        assert close is None

    def test_convert_roc_date(self, temp_dirs):
        """Test ROC date conversion."""
        loader = HistoricalDataLoader(**temp_dirs)

        # Normal case
        result = loader._convert_roc_date('115/02/09')
        assert result == date(2026, 2, 9)

        # With quotes
        result = loader._convert_roc_date('"115/02/10"')
        assert result == date(2026, 2, 10)

        # Year 100 (2011)
        result = loader._convert_roc_date('100/01/01')
        assert result == date(2011, 1, 1)

    def test_get_available_dates(self, temp_dirs):
        """Test getting available dates."""
        loader = HistoricalDataLoader(**temp_dirs)
        dates = loader.get_available_dates()

        assert '2026-02-10' in dates
        assert len(dates) == 1  # Only date with both TX and TXO

    def test_get_available_dates_empty(self):
        """Test getting available dates with empty folders."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tx_path = os.path.join(tmpdir, 'tx')
            txo_path = os.path.join(tmpdir, 'txo')
            taiex_path = os.path.join(tmpdir, 'taiex')
            os.makedirs(tx_path)
            os.makedirs(txo_path)
            os.makedirs(taiex_path)

            loader = HistoricalDataLoader(tx_path, txo_path, taiex_path)
            dates = loader.get_available_dates()

            assert dates == []
