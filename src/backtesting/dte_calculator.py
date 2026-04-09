"""DTE (Days To Expiration) calculator for backtesting.

Calculates the number of days until contract expiration based on
hardcoded expiration dates.
"""

from datetime import datetime, date
from typing import Optional

# Hardcoded expiration dates (to be updated as needed)
EXPIRATION_DATES = {
    (2026, 2): date(2026, 2, 23),   # February 2026 contract
    (2026, 3): date(2026, 3, 18),   # March 2026 contract
    (2026, 4): date(2026, 4, 15),   # April 2026 contract
}


def get_expiration_date(data_date: date) -> Optional[date]:
    """Get the expiration date for a given data date.

    Logic:
    - If data_date is before or on the current month's expiration,
      use current month's expiration
    - If data_date is after current month's expiration,
      use next month's expiration

    Args:
        data_date: The date of the data being processed

    Returns:
        Expiration date, or None if not found in config
    """
    year = data_date.year
    month = data_date.month

    # Check current month's expiration
    current_exp = EXPIRATION_DATES.get((year, month))

    if current_exp and data_date <= current_exp:
        return current_exp

    # Need to use next month's expiration
    next_month = month + 1
    next_year = year
    if next_month > 12:
        next_month = 1
        next_year += 1

    next_exp = EXPIRATION_DATES.get((next_year, next_month))
    if next_exp:
        return next_exp

    # Fallback: return current month if available
    return current_exp


def get_dte(data_date_str: str) -> Optional[int]:
    """Calculate DTE (days to expiration) for a given date.

    Args:
        data_date_str: Date string in YYYY-MM-DD format

    Returns:
        Number of days until expiration, or None if expiration not found
    """
    data_date = datetime.strptime(data_date_str, '%Y-%m-%d').date()
    exp_date = get_expiration_date(data_date)

    if exp_date is None:
        return None

    dte = (exp_date - data_date).days
    return max(0, dte)  # Don't return negative DTE


def get_dte_from_date(data_date: date) -> Optional[int]:
    """Calculate DTE from a date object.

    Args:
        data_date: Date object

    Returns:
        Number of days until expiration, or None if expiration not found
    """
    exp_date = get_expiration_date(data_date)

    if exp_date is None:
        return None

    dte = (exp_date - data_date).days
    return max(0, dte)
