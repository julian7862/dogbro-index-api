#!/usr/bin/env python3
"""Backtesting CLI for historical IV indicator calculation.

Usage:
    python main_backtest.py \
        --tx-path /path/to/tx_5min_kbar \
        --txo-path /path/to/txo_5min_kbar \
        --taiex-path /path/to/TAIEX_HIST \
        --start 2026-02-10 \
        --end 2026-03-31 \
        --collection backtest_results
"""

import argparse
import logging
import os
import sys
import time
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.backtesting.data_loader import HistoricalDataLoader
from src.backtesting.backtest_runner import BacktestRunner
from src.backtesting.result_store import BacktestResultStore

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Backtest IV indicators using historical data'
    )
    parser.add_argument(
        '--tx-path',
        required=True,
        help='Path to TX futures 5-min kbar CSV folder'
    )
    parser.add_argument(
        '--txo-path',
        required=True,
        help='Path to TXO options 5-min kbar CSV folder'
    )
    parser.add_argument(
        '--taiex-path',
        required=True,
        help='Path to TAIEX closing index CSV folder'
    )
    parser.add_argument(
        '--start',
        required=True,
        help='Start date (YYYY-MM-DD)'
    )
    parser.add_argument(
        '--end',
        required=True,
        help='End date (YYYY-MM-DD)'
    )
    parser.add_argument(
        '--collection',
        default='backtest_results',
        help='MongoDB collection name (default: backtest_results)'
    )
    parser.add_argument(
        '--mongo-uri',
        default=os.getenv('MONGO_URI'),
        help='MongoDB connection URI (default: from MONGO_URI env var)'
    )
    return parser.parse_args()


def validate_paths(args):
    """Validate that all paths exist."""
    paths = [
        ('TX path', args.tx_path),
        ('TXO path', args.txo_path),
        ('TAIEX path', args.taiex_path),
    ]
    for name, path in paths:
        if not os.path.exists(path):
            logger.error(f"{name} does not exist: {path}")
            return False
    return True


def validate_dates(args):
    """Validate date format and range."""
    try:
        start = datetime.strptime(args.start, '%Y-%m-%d')
        end = datetime.strptime(args.end, '%Y-%m-%d')
        if start > end:
            logger.error("Start date must be before or equal to end date")
            return False
        return True
    except ValueError as e:
        logger.error(f"Invalid date format: {e}")
        return False


def main():
    """Main entry point."""
    args = parse_args()

    # Validate inputs
    if not validate_paths(args):
        sys.exit(1)
    if not validate_dates(args):
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("Backtesting IV Indicators")
    logger.info("=" * 60)
    logger.info(f"TX path:     {args.tx_path}")
    logger.info(f"TXO path:    {args.txo_path}")
    logger.info(f"TAIEX path:  {args.taiex_path}")
    logger.info(f"Date range:  {args.start} to {args.end}")
    logger.info(f"Collection:  {args.collection}")
    logger.info("=" * 60)

    start_time = time.time()

    # Initialize components
    data_loader = HistoricalDataLoader(
        tx_path=args.tx_path,
        txo_path=args.txo_path,
        taiex_path=args.taiex_path
    )

    result_store = BacktestResultStore(
        mongo_uri=args.mongo_uri,
        collection_name=args.collection
    )

    runner = BacktestRunner(
        data_loader=data_loader,
        result_store=result_store
    )

    # Run backtest
    summary = runner.run_range(args.start, args.end)

    # Output summary
    elapsed = time.time() - start_time
    logger.info("=" * 60)
    logger.info("Backtest Complete")
    logger.info("=" * 60)
    logger.info(f"Days processed:  {summary['days_processed']}")
    logger.info(f"Total bars:      {summary['total_bars']}")
    logger.info(f"Elapsed time:    {elapsed:.2f} seconds")
    logger.info("=" * 60)

    # Cleanup
    result_store.close()


if __name__ == '__main__':
    main()
