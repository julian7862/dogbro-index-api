"""Unit tests for BacktestResultStore."""

import pytest
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock
import os

from src.backtesting.result_store import BacktestResultStore
from src.backtesting.backtest_runner import BacktestBarResult


class TestBacktestResultStore:
    """Tests for BacktestResultStore class."""

    @pytest.fixture
    def mock_result(self):
        """Create a mock BacktestBarResult."""
        return BacktestBarResult(
            datetime=datetime(2026, 2, 10, 8, 45),
            date_str='2026-02-10',
            underlying_price=32700.0,
            civ=25.5,
            civ_ma5=25.2,
            civ_pb=45.0,
            price_pb=42.0,
            pb_minus_civ_pb=-3.0,
            dte=13,
            valid_iv_count=14
        )

    def test_init_without_uri(self):
        """Test initialization without MongoDB URI."""
        # Clear MONGO_URI env var if set
        env_backup = os.environ.get('MONGO_URI')
        if 'MONGO_URI' in os.environ:
            del os.environ['MONGO_URI']
        try:
            store = BacktestResultStore(mongo_uri=None)
            assert store._collection is None
        finally:
            if env_backup:
                os.environ['MONGO_URI'] = env_backup

    def test_save_results_with_mock_collection(self, mock_result):
        """Test saving results with manually set collection."""
        mock_collection = MagicMock()
        mock_collection.insert_many.return_value = MagicMock(inserted_ids=['id1'])

        store = BacktestResultStore(mongo_uri=None)
        store._collection = mock_collection

        count = store.save_results('2026-02-10', [mock_result])

        assert count == 1
        mock_collection.delete_many.assert_called_once()  # Clear first
        mock_collection.insert_many.assert_called_once()

    def test_save_results_empty_list(self):
        """Test saving empty results list."""
        mock_collection = MagicMock()

        store = BacktestResultStore(mongo_uri=None)
        store._collection = mock_collection

        count = store.save_results('2026-02-10', [])

        assert count == 0
        mock_collection.insert_many.assert_not_called()

    def test_clear_date(self):
        """Test clearing results for a date."""
        mock_collection = MagicMock()
        mock_collection.delete_many.return_value = MagicMock(deleted_count=5)

        store = BacktestResultStore(mongo_uri=None)
        store._collection = mock_collection

        count = store.clear_date('2026-02-10')

        assert count == 5
        mock_collection.delete_many.assert_called_once_with({"date": "2026-02-10"})

    def test_get_results_by_date(self):
        """Test querying results by date."""
        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = mock_cursor
        mock_cursor.__iter__ = Mock(return_value=iter([{'date': '2026-02-10'}]))

        mock_collection = MagicMock()
        mock_collection.find.return_value = mock_cursor

        store = BacktestResultStore(mongo_uri=None)
        store._collection = mock_collection

        results = store.get_results(date_str='2026-02-10')

        mock_collection.find.assert_called_once_with({"date": "2026-02-10"})
        assert len(results) == 1

    def test_count_results(self):
        """Test counting results."""
        mock_collection = MagicMock()
        mock_collection.count_documents.return_value = 42

        store = BacktestResultStore(mongo_uri=None)
        store._collection = mock_collection

        count = store.count_results('2026-02-10')

        assert count == 42

    def test_save_without_connection(self, mock_result):
        """Test save when not connected to MongoDB."""
        # Clear MONGO_URI env var if set
        env_backup = os.environ.get('MONGO_URI')
        if 'MONGO_URI' in os.environ:
            del os.environ['MONGO_URI']
        try:
            store = BacktestResultStore(mongo_uri=None)
            count = store.save_results('2026-02-10', [mock_result])
            assert count == 0
        finally:
            if env_backup:
                os.environ['MONGO_URI'] = env_backup

    def test_clear_without_connection(self):
        """Test clear when not connected to MongoDB."""
        # Clear MONGO_URI env var if set
        env_backup = os.environ.get('MONGO_URI')
        if 'MONGO_URI' in os.environ:
            del os.environ['MONGO_URI']
        try:
            store = BacktestResultStore(mongo_uri=None)
            count = store.clear_date('2026-02-10')
            assert count == 0
        finally:
            if env_backup:
                os.environ['MONGO_URI'] = env_backup

    def test_get_results_without_connection(self):
        """Test query when not connected to MongoDB."""
        # Clear MONGO_URI env var if set
        env_backup = os.environ.get('MONGO_URI')
        if 'MONGO_URI' in os.environ:
            del os.environ['MONGO_URI']
        try:
            store = BacktestResultStore(mongo_uri=None)
            results = store.get_results(date_str='2026-02-10')
            assert results == []
        finally:
            if env_backup:
                os.environ['MONGO_URI'] = env_backup
