"""Backtest runner for IV indicator calculation.

Orchestrates the backtesting process:
1. Load historical data
2. Calculate CIV and Bollinger %b indicators
3. Store results to MongoDB
"""

import logging
from dataclasses import dataclass
from datetime import datetime, date
from typing import Dict, List, Optional, Any

import pandas as pd

from src.backtesting.data_loader import HistoricalDataLoader
from src.backtesting.result_store import BacktestResultStore
from src.backtesting.dte_calculator import get_dte
from src.utils.strike_calculator import calculate_call_strikes
from src.indicators.iv_calculator import (
    calc_civ_from_option_quotes,
    calc_indicator_for_bar,
    IndicatorResult,
)

logger = logging.getLogger(__name__)


@dataclass
class BacktestBarResult:
    """Result for a single 5-min bar."""
    datetime: datetime
    date_str: str
    underlying_price: float
    civ: Optional[float]
    civ_ma5: Optional[float]
    civ_pb: Optional[float]
    price_pb: Optional[float]
    pb_minus_civ_pb: Optional[float]
    dte: int
    valid_iv_count: int


class BacktestRunner:
    """Run backtests on historical data."""

    def __init__(
        self,
        data_loader: HistoricalDataLoader,
        result_store: Optional[BacktestResultStore] = None
    ):
        """Initialize the backtest runner.

        Args:
            data_loader: Historical data loader instance
            result_store: Optional result store for MongoDB persistence
        """
        self.data_loader = data_loader
        self.result_store = result_store

        # History for Bollinger calculation
        self._civ_history: List[float] = []
        self._price_history: List[float] = []

    def run_range(
        self,
        start_date: str,
        end_date: str
    ) -> Dict[str, Any]:
        """Run backtest for a date range.

        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)

        Returns:
            Summary dict with days_processed, total_bars
        """
        # Get available dates within range
        all_dates = self.data_loader.get_available_dates()

        # Filter to requested range
        dates_in_range = [
            d for d in all_dates
            if start_date <= d <= end_date
        ]

        if not dates_in_range:
            logger.warning(f"No data found in range {start_date} to {end_date}")
            return {'days_processed': 0, 'total_bars': 0}

        logger.info(f"Found {len(dates_in_range)} trading days in range")

        days_processed = 0
        total_bars = 0

        for date_str in dates_in_range:
            logger.info(f"Processing {date_str}...")
            results = self.run_date(date_str)

            if results:
                days_processed += 1
                total_bars += len(results)

                # Save to MongoDB if store is available
                if self.result_store:
                    self.result_store.save_results(date_str, results)

            logger.info(f"  -> {len(results)} bars processed")

        return {
            'days_processed': days_processed,
            'total_bars': total_bars,
        }

    def run_date(self, date_str: str) -> List[BacktestBarResult]:
        """Run backtest for a single date.

        Args:
            date_str: Date string (YYYY-MM-DD)

        Returns:
            List of BacktestBarResult for each 5-min bar
        """
        # Get previous trading day's closing index for strike calculation
        prev_close = self._get_previous_close(date_str)
        if prev_close is None:
            logger.warning(f"No previous close found for {date_str}, skipping")
            return []

        # Calculate strikes (ATM ± 8)
        strikes = calculate_call_strikes(prev_close, num_strikes=8)
        logger.debug(f"Using strikes: {strikes[0]} to {strikes[-1]}")

        # Load day's data
        tx_df, txo_df = self._prepare_day_data(date_str)
        if tx_df.empty or txo_df.empty:
            logger.warning(f"Missing data for {date_str}")
            return []

        # Filter TXO to only include our strikes
        txo_df = txo_df[txo_df['strike'].isin(strikes)]

        # Get DTE for this date
        dte = get_dte(date_str)
        if dte is None:
            logger.warning(f"No DTE config for {date_str}, using default 15")
            dte = 15

        # Get unique bar times from TX data
        bar_times = tx_df['datetime'].unique()

        results = []
        for bar_time in sorted(bar_times):
            result = self._calc_bar_indicators(
                bar_time=pd.Timestamp(bar_time),
                date_str=date_str,
                tx_df=tx_df,
                txo_df=txo_df,
                strikes=strikes,
                dte=dte
            )
            if result:
                results.append(result)

        return results

    def _prepare_day_data(
        self,
        date_str: str
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Load and prepare data for a single day.

        Args:
            date_str: Date string (YYYY-MM-DD)

        Returns:
            Tuple of (tx_df, txo_df)
        """
        tx_df = self.data_loader.load_tx_bars(date_str)
        txo_df = self.data_loader.load_txo_bars(date_str)
        return tx_df, txo_df

    def _get_previous_close(self, date_str: str) -> Optional[float]:
        """Get previous trading day's TAIEX close.

        For now, uses a simple approach: try previous calendar days
        until we find data or give up after 7 days.

        Args:
            date_str: Current date string (YYYY-MM-DD)

        Returns:
            Previous day's closing index, or None if not found
        """
        current = datetime.strptime(date_str, '%Y-%m-%d').date()

        # Try up to 7 previous days
        for i in range(1, 8):
            prev_date = date(
                current.year,
                current.month,
                current.day
            )
            # Subtract days manually to handle month boundaries
            from datetime import timedelta
            prev_date = current - timedelta(days=i)
            prev_str = prev_date.strftime('%Y-%m-%d')

            close = self.data_loader.load_taiex_close(prev_str)
            if close is not None:
                return close

        return None

    def _calc_bar_indicators(
        self,
        bar_time: pd.Timestamp,
        date_str: str,
        tx_df: pd.DataFrame,
        txo_df: pd.DataFrame,
        strikes: List[int],
        dte: int
    ) -> Optional[BacktestBarResult]:
        """Calculate indicators for a single 5-min bar.

        Args:
            bar_time: Timestamp of the bar
            date_str: Date string for the bar
            tx_df: TX futures DataFrame
            txo_df: TXO options DataFrame (already filtered to strikes)
            strikes: List of strike prices
            dte: Days to expiration

        Returns:
            BacktestBarResult or None if calculation failed
        """
        # Get underlying price at this bar time
        tx_at_bar = tx_df[tx_df['datetime'] == bar_time]
        if tx_at_bar.empty:
            return None
        underlying_price = float(tx_at_bar.iloc[0]['price'])

        # Get option prices at this bar time
        txo_at_bar = txo_df[txo_df['datetime'] == bar_time]
        if txo_at_bar.empty:
            return None

        # Build option_closes dict for calc_civ_from_option_quotes
        # The function expects {contract_code: price} format
        # We'll use strike as a pseudo contract code
        option_closes = {}
        valid_count = 0
        for _, row in txo_at_bar.iterrows():
            strike = int(row['strike'])
            price = float(row['price'])
            if price > 0:
                # Use TXO{strike}X0 format for compatibility
                code = f"TXO{strike}X0"
                option_closes[code] = price
                valid_count += 1

        # Calculate CIV
        civ = calc_civ_from_option_quotes(
            option_closes=option_closes,
            strikes=strikes,
            underlying_price=underlying_price,
            dte=dte
        )

        if civ is None:
            # Still record the bar but with None CIV
            return BacktestBarResult(
                datetime=bar_time.to_pydatetime(),
                date_str=date_str,
                underlying_price=underlying_price,
                civ=None,
                civ_ma5=None,
                civ_pb=None,
                price_pb=None,
                pb_minus_civ_pb=None,
                dte=dte,
                valid_iv_count=valid_count
            )

        # Add to history
        self._civ_history.append(civ)
        self._price_history.append(underlying_price)

        # Calculate full indicators if we have enough history
        indicator = None
        if len(self._civ_history) >= 5:  # Need at least 5 for MA5
            indicator = calc_indicator_for_bar(
                civ=civ,
                civ_history=self._civ_history[:-1],  # Exclude current
                price=underlying_price,
                price_history=self._price_history[:-1],
                period=20
            )

        return BacktestBarResult(
            datetime=bar_time.to_pydatetime(),
            date_str=date_str,
            underlying_price=underlying_price,
            civ=civ,
            civ_ma5=indicator.civ_ma5 if indicator else None,
            civ_pb=indicator.civ_pb if indicator else None,
            price_pb=indicator.price_pb if indicator else None,
            pb_minus_civ_pb=indicator.pb_minus_civ_pb if indicator else None,
            dte=dte,
            valid_iv_count=valid_count
        )

    def reset_history(self) -> None:
        """Reset CIV and price history.

        Call this when starting a new backtest to clear accumulated history.
        """
        self._civ_history = []
        self._price_history = []
