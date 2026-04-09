"""Historical data loader for backtesting.

Reads CSV files from TAIFEX historical data folders:
- TX futures 5-min kbar
- TXO options 5-min kbar
- TAIEX closing index
"""

import logging
import os
import re
from datetime import datetime, date
from typing import Optional, List

import pandas as pd

logger = logging.getLogger(__name__)


class HistoricalDataLoader:
    """Load historical market data from CSV files."""

    def __init__(
        self,
        tx_path: str,
        txo_path: str,
        taiex_path: str
    ):
        """Initialize the data loader.

        Args:
            tx_path: Path to TX futures 5-min kbar folder
            txo_path: Path to TXO options 5-min kbar folder
            taiex_path: Path to TAIEX closing index folder
        """
        self.tx_path = tx_path
        self.txo_path = txo_path
        self.taiex_path = taiex_path

        # Cache for TAIEX data (loaded once)
        self._taiex_cache: Optional[pd.DataFrame] = None

    def load_tx_bars(self, date_str: str) -> pd.DataFrame:
        """Load TX futures 5-min kbar data for a specific date.

        Args:
            date_str: Date string in YYYY-MM-DD format

        Returns:
            DataFrame with columns: datetime, price
            Empty DataFrame if file not found
        """
        # Convert date format: 2026-02-10 -> tx_5min_kbar_2026_02_10.csv
        dt = datetime.strptime(date_str, '%Y-%m-%d')
        filename = f"tx_5min_kbar_{dt.year}_{dt.month:02d}_{dt.day:02d}.csv"
        filepath = os.path.join(self.tx_path, filename)

        if not os.path.exists(filepath):
            logger.warning(f"TX file not found: {filepath}")
            return pd.DataFrame(columns=['datetime', 'price'])

        try:
            df = pd.read_csv(filepath)
            df['datetime'] = pd.to_datetime(df['datetime'])
            return df
        except Exception as e:
            logger.error(f"Error loading TX file {filepath}: {e}")
            return pd.DataFrame(columns=['datetime', 'price'])

    def load_txo_bars(self, date_str: str) -> pd.DataFrame:
        """Load TXO options 5-min kbar data for a specific date.

        Args:
            date_str: Date string in YYYY-MM-DD format

        Returns:
            DataFrame with columns: datetime, strike, price
            Empty DataFrame if file not found
        """
        # Convert date format: 2026-02-10 -> 5min_kbar_2026_02_10.csv
        dt = datetime.strptime(date_str, '%Y-%m-%d')
        filename = f"5min_kbar_{dt.year}_{dt.month:02d}_{dt.day:02d}.csv"
        filepath = os.path.join(self.txo_path, filename)

        if not os.path.exists(filepath):
            logger.warning(f"TXO file not found: {filepath}")
            return pd.DataFrame(columns=['datetime', 'strike', 'price'])

        try:
            df = pd.read_csv(filepath)
            df['datetime'] = pd.to_datetime(df['datetime'])
            return df
        except Exception as e:
            logger.error(f"Error loading TXO file {filepath}: {e}")
            return pd.DataFrame(columns=['datetime', 'strike', 'price'])

    def load_taiex_close(self, date_str: str) -> Optional[float]:
        """Load TAIEX closing index for a specific date.

        Args:
            date_str: Date string in YYYY-MM-DD format

        Returns:
            Closing index value, or None if not found
        """
        # Ensure TAIEX data is loaded
        if self._taiex_cache is None:
            self._load_taiex_data()

        if self._taiex_cache is None or self._taiex_cache.empty:
            return None

        # Find the row for the given date
        dt = datetime.strptime(date_str, '%Y-%m-%d').date()
        matching = self._taiex_cache[self._taiex_cache['date'] == dt]

        if matching.empty:
            logger.warning(f"TAIEX data not found for date: {date_str}")
            return None

        return float(matching.iloc[0]['close'])

    def _load_taiex_data(self) -> None:
        """Load all TAIEX CSV files into cache."""
        all_data = []

        for filename in os.listdir(self.taiex_path):
            if not filename.startswith('TAIEX_HIST_') or not filename.endswith('.csv'):
                continue

            filepath = os.path.join(self.taiex_path, filename)
            try:
                # Read with Big5 encoding (Taiwan traditional Chinese)
                # Use usecols to select only the first 5 columns (ignore trailing comma)
                df = pd.read_csv(
                    filepath,
                    encoding='big5',
                    skiprows=1,
                    usecols=[0, 1, 2, 3, 4]
                )

                # Rename columns (original: 日期, 開盤指數, 最高指數, 最低指數, 收盤指數)
                df.columns = ['date', 'open', 'high', 'low', 'close']

                # Convert ROC year to AD year (115/02/09 -> 2026-02-09)
                df['date'] = df['date'].apply(self._convert_roc_date)

                # Remove commas from numeric columns and convert to float
                for col in ['open', 'high', 'low', 'close']:
                    df[col] = df[col].astype(str).str.replace(',', '').astype(float)

                all_data.append(df)
            except Exception as e:
                logger.error(f"Error loading TAIEX file {filepath}: {e}")

        if all_data:
            self._taiex_cache = pd.concat(all_data, ignore_index=True)
            self._taiex_cache = self._taiex_cache.sort_values('date').reset_index(drop=True)
            logger.info(f"Loaded {len(self._taiex_cache)} TAIEX records")
        else:
            self._taiex_cache = pd.DataFrame(columns=['date', 'open', 'high', 'low', 'close'])

    def _convert_roc_date(self, roc_date_str: str) -> date:
        """Convert ROC (Taiwan) date to AD date.

        Args:
            roc_date_str: Date in ROC format (e.g., "115/02/09")

        Returns:
            Python date object
        """
        # Remove quotes if present
        roc_date_str = roc_date_str.strip('"').strip()

        # Parse ROC date
        match = re.match(r'(\d+)/(\d+)/(\d+)', roc_date_str)
        if not match:
            raise ValueError(f"Invalid ROC date format: {roc_date_str}")

        roc_year = int(match.group(1))
        month = int(match.group(2))
        day = int(match.group(3))

        # Convert to AD year (ROC year + 1911)
        ad_year = roc_year + 1911

        return date(ad_year, month, day)

    def get_available_dates(self) -> List[str]:
        """Get list of dates that have both TX and TXO data.

        Returns:
            List of date strings in YYYY-MM-DD format
        """
        # Get TX dates
        tx_dates = set()
        for filename in os.listdir(self.tx_path):
            match = re.match(r'tx_5min_kbar_(\d{4})_(\d{2})_(\d{2})\.csv', filename)
            if match:
                date_str = f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
                tx_dates.add(date_str)

        # Get TXO dates
        txo_dates = set()
        for filename in os.listdir(self.txo_path):
            match = re.match(r'5min_kbar_(\d{4})_(\d{2})_(\d{2})\.csv', filename)
            if match:
                date_str = f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
                txo_dates.add(date_str)

        # Return intersection (dates with both TX and TXO data)
        common_dates = tx_dates & txo_dates
        return sorted(list(common_dates))
