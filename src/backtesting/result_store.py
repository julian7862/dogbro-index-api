"""Backtest result store for MongoDB persistence.

Stores backtest results to MongoDB for later analysis.
"""

import logging
import os
from datetime import datetime
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.backtesting.backtest_runner import BacktestBarResult

logger = logging.getLogger(__name__)


class BacktestResultStore:
    """Store backtest results to MongoDB."""

    def __init__(
        self,
        mongo_uri: Optional[str] = None,
        db_name: str = 'market_data',
        collection_name: str = 'backtest_results'
    ):
        """Initialize the result store.

        Args:
            mongo_uri: MongoDB connection string (default: from MONGO_URI env)
            db_name: Database name (default: market_data)
            collection_name: Collection name (default: backtest_results)
        """
        self._mongo_uri = mongo_uri or os.getenv('MONGO_URI')
        self._db_name = db_name
        self._collection_name = collection_name
        self._client = None
        self._collection = None

        if self._mongo_uri:
            self._init_mongodb()
        else:
            logger.warning("No MongoDB URI provided, results will not be persisted")

    def _init_mongodb(self) -> None:
        """Initialize MongoDB connection."""
        try:
            from pymongo import MongoClient
            self._client = MongoClient(self._mongo_uri)
            db = self._client[self._db_name]
            self._collection = db[self._collection_name]

            # Create indexes
            self._collection.create_index([("datetime", -1)])
            self._collection.create_index([("date", 1)])

            logger.info(
                f"BacktestResultStore: Connected to {self._db_name}.{self._collection_name}"
            )
        except Exception as e:
            logger.error(f"BacktestResultStore: MongoDB connection failed: {e}")
            self._collection = None

    def save_results(
        self,
        date_str: str,
        results: List["BacktestBarResult"]
    ) -> int:
        """Save backtest results for a date.

        Clears existing data for the date before inserting new data.

        Args:
            date_str: Date string (YYYY-MM-DD)
            results: List of BacktestBarResult

        Returns:
            Number of documents inserted
        """
        if self._collection is None:
            logger.warning("MongoDB not connected, skipping save")
            return 0

        if not results:
            return 0

        # Clear existing data for this date
        self.clear_date(date_str)

        # Convert results to documents
        documents = []
        for r in results:
            doc = {
                "datetime": r.datetime,
                "date": r.date_str,
                "underlying_price": r.underlying_price,
                "civ": r.civ,
                "civ_ma5": r.civ_ma5,
                "civ_pb": r.civ_pb,
                "price_pb": r.price_pb,
                "pb_minus_civ_pb": r.pb_minus_civ_pb,
                "dte": r.dte,
                "valid_iv_count": r.valid_iv_count,
            }
            documents.append(doc)

        try:
            result = self._collection.insert_many(documents)
            inserted = len(result.inserted_ids)
            logger.info(f"Saved {inserted} results for {date_str}")
            return inserted
        except Exception as e:
            logger.error(f"Failed to save results for {date_str}: {e}")
            return 0

    def clear_date(self, date_str: str) -> int:
        """Clear all results for a specific date.

        Args:
            date_str: Date string (YYYY-MM-DD)

        Returns:
            Number of documents deleted
        """
        if self._collection is None:
            return 0

        try:
            result = self._collection.delete_many({"date": date_str})
            if result.deleted_count > 0:
                logger.info(f"Cleared {result.deleted_count} existing results for {date_str}")
            return result.deleted_count
        except Exception as e:
            logger.error(f"Failed to clear results for {date_str}: {e}")
            return 0

    def get_results(
        self,
        date_str: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 0
    ) -> List[dict]:
        """Query stored results.

        Args:
            date_str: Specific date to query (YYYY-MM-DD)
            start_date: Start of date range
            end_date: End of date range
            limit: Maximum number of results (0 = no limit)

        Returns:
            List of result documents
        """
        if self._collection is None:
            return []

        query = {}
        if date_str:
            query["date"] = date_str
        elif start_date or end_date:
            query["date"] = {}
            if start_date:
                query["date"]["$gte"] = start_date
            if end_date:
                query["date"]["$lte"] = end_date

        try:
            cursor = self._collection.find(query).sort("datetime", 1)
            if limit > 0:
                cursor = cursor.limit(limit)
            return list(cursor)
        except Exception as e:
            logger.error(f"Failed to query results: {e}")
            return []

    def count_results(self, date_str: Optional[str] = None) -> int:
        """Count stored results.

        Args:
            date_str: Optional date to filter (YYYY-MM-DD)

        Returns:
            Number of documents
        """
        if self._collection is None:
            return 0

        try:
            query = {"date": date_str} if date_str else {}
            return self._collection.count_documents(query)
        except Exception as e:
            logger.error(f"Failed to count results: {e}")
            return 0

    def close(self) -> None:
        """Close MongoDB connection."""
        if self._client:
            try:
                self._client.close()
                logger.info("BacktestResultStore: Connection closed")
            except Exception as e:
                logger.error(f"Error closing connection: {e}")
