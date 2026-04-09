"""Unit tests for DTE calculator."""

import pytest
from datetime import date

from src.backtesting.dte_calculator import (
    get_dte,
    get_dte_from_date,
    get_expiration_date,
    EXPIRATION_DATES,
)


class TestDTECalculator:
    """Tests for DTE calculator functions."""

    def test_get_dte_february_data(self):
        """Test DTE for February 2026 data (before expiration)."""
        # 2026-02-10 to 2026-02-23 = 13 days
        dte = get_dte('2026-02-10')
        assert dte == 13

    def test_get_dte_february_data_later(self):
        """Test DTE for later February date."""
        # 2026-02-20 to 2026-02-23 = 3 days
        dte = get_dte('2026-02-20')
        assert dte == 3

    def test_get_dte_march_data(self):
        """Test DTE for March 2026 data."""
        # 2026-03-10 to 2026-03-18 = 8 days
        dte = get_dte('2026-03-10')
        assert dte == 8

    def test_get_dte_after_february_expiration(self):
        """Test DTE after February expiration should use March."""
        # 2026-02-24 is after 2/23 expiration, so use 3/18
        # 2026-02-24 to 2026-03-18 = 22 days
        dte = get_dte('2026-02-24')
        assert dte == 22

    def test_get_dte_on_expiration_day(self):
        """Test DTE on expiration day."""
        # 2026-02-23 to 2026-02-23 = 0 days
        dte = get_dte('2026-02-23')
        assert dte == 0

    def test_get_expiration_date_february(self):
        """Test getting expiration date for February data."""
        exp = get_expiration_date(date(2026, 2, 10))
        assert exp == date(2026, 2, 23)

    def test_get_expiration_date_after_expiry(self):
        """Test getting expiration when past current month's expiry."""
        # 2026-02-24 is after 2/23, should return March expiration
        exp = get_expiration_date(date(2026, 2, 24))
        assert exp == date(2026, 3, 18)

    def test_get_expiration_date_march(self):
        """Test getting expiration date for March data."""
        exp = get_expiration_date(date(2026, 3, 10))
        assert exp == date(2026, 3, 18)

    def test_get_expiration_date_after_march_expiry(self):
        """Test getting April expiration after March expiry."""
        # 2026-03-19 is after 3/18, should return April expiration
        exp = get_expiration_date(date(2026, 3, 19))
        assert exp == date(2026, 4, 15)

    def test_get_dte_from_date(self):
        """Test get_dte_from_date function."""
        dte = get_dte_from_date(date(2026, 2, 10))
        assert dte == 13

    def test_hardcoded_expiration_dates(self):
        """Verify hardcoded expiration dates are correct."""
        assert EXPIRATION_DATES[(2026, 2)] == date(2026, 2, 23)
        assert EXPIRATION_DATES[(2026, 3)] == date(2026, 3, 18)
        assert EXPIRATION_DATES[(2026, 4)] == date(2026, 4, 15)

    def test_get_dte_unknown_date(self):
        """Test DTE for date not in config."""
        # 2025-01-01 is not configured
        dte = get_dte('2025-01-01')
        assert dte is None
