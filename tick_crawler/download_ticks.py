#!/usr/bin/env python3
"""Download a conservative, resumable archive. See docs/HISTORICAL_TICKS.md."""

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

from src.data.tick_archive import Archive, ArchiveStop, Calendar, Downloader, Policy, TAIPEI, MIB, check_window, single_worker

PROJECT = Path(__file__).resolve().parent


def parser():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--output', type=Path, help='archive directory; required explicitly for run (use your external disk)')
    cli.add_argument('--calendar', type=Path, default=PROJECT / 'data' / 'reference' / 'twse_holidays_2026.json')
    cli.add_argument('--env', type=Path, default=PROJECT / '.env')
    commands = cli.add_subparsers(dest='command', required=True)
    plan = commands.add_parser('plan', help='cache current ordinary share list; build manifest without broker login')
    plan.add_argument('--start', type=date.fromisoformat, default=date(2026, 3, 1))
    plan.add_argument('--end', type=date.fromisoformat, default=date(2026, 9, 24))
    plan.add_argument('--codes', help='optional comma-separated stock codes for a smaller archive')
    plan.add_argument('--market', choices=('both', 'TSE', 'OTC'), default='both')
    plan.add_argument('--refresh-universe', action='store_true')
    plan.add_argument('--universe', type=Path, help='verified historical universe JSON instead of current exchange list')
    commands.add_parser('status', help='local progress, no login')
    commands.add_parser('usage', help='one login and quota check, no ticks/contracts/orders')
    commands.add_parser('verify', help='verify saved file checksums, no network')
    run = commands.add_parser('run', help='one bounded batch, only between 16:00 and 08:00 Taiwan time')
    run.add_argument('--max-requests', type=int, default=1000)
    run.add_argument('--interval', type=float, default=5)
    run.add_argument('--daily-mib', type=int, default=200)
    clear = commands.add_parser('clear-halt', help='record diagnosis before allowing another batch')
    clear.add_argument('--reason', required=True)
    clear.add_argument('--retry-failed', action='store_true', help='put failed job back into pending; otherwise retain the coverage gap')
    return cli


def main(argv=None):
    args = parser().parse_args(argv)
    explicit_output = args.output is not None
    args.output = args.output or PROJECT / 'data' / 'historical_ticks'
    report = {}
    exit_code = 0
    archive = None
    try:
        with single_worker(PROJECT / '.cache' / 'shioaji-history.lock'):
            archive = Archive(args.output)
            if args.command == 'plan':
                from src.data.equity_universe import load_universe
                calendar = Calendar(args.calendar)
                # Validate dates before doing external work.
                list(calendar.days(args.start, args.end))
                if args.end > datetime.now(TAIPEI).date():
                    raise ValueError('end date cannot be in the future')
                payload = (json.loads(args.universe.read_text()) if args.universe else
                           load_universe(args.output / 'universe.json', args.refresh_universe))
                stocks = [s for s in payload['stocks'] if args.market == 'both' or s['exchange'] == args.market]
                if args.codes:
                    codes = {c.strip() for c in args.codes.split(',') if c.strip()}
                    stocks = [s for s in stocks if s['code'] in codes]
                    if codes - {s['code'] for s in stocks}:
                        raise ValueError('some requested codes are absent from the current ordinary-share universe')
                if not stocks:
                    raise ValueError('empty universe')
                archive.plan(stocks, calendar, args.start, args.end)
                archive.set_meta('universe_as_of', payload['as_of'])
                report = archive.summary()
            elif args.command == 'status':
                report = archive.summary()
            elif args.command == 'verify':
                report = {'verified_files': archive.verify()}
            elif args.command == 'clear-halt':
                archive.clear_halt(args.reason, args.retry_failed)
                report = archive.summary()
            elif args.command == 'usage':
                from src.data.shioaji_history import open_history_api
                with open_history_api(args.env) as api:
                    report = {'sdk_version': api.version, 'usage': api.usage()}
                archive.set_meta('last_usage', report['usage'])
            elif args.command == 'run':
                if not explicit_output:
                    raise ArchiveStop('run requires --output pointing to your external disk archive')
                policy = Policy(interval=args.interval, daily_bytes=args.daily_mib * MIB)
                if not 1 <= args.max_requests <= 1000:
                    raise ValueError('max-requests must be 1..1000')
                check_window(datetime.now(TAIPEI))  # Refuse before login.
                if archive.meta('halt'):
                    raise ArchiveStop('previous error requires diagnosis; see status and clear-halt')
                if not archive.db.execute('SELECT 1 FROM jobs WHERE status IN ("pending","in_flight") LIMIT 1').fetchone():
                    raise ArchiveStop('no pending jobs; inspect status or create a plan')
                calendar = Calendar(args.calendar)
                from src.data.shioaji_history import open_history_api
                with open_history_api(args.env) as api:
                    count = Downloader(archive, api, calendar, policy).run(args.max_requests)
                report = {'requested_this_run': count, **archive.summary()}
    except ArchiveStop as exc:
        report = {'stopped': str(exc), **(archive.summary() if archive else {})}
        exit_code = 2
    except Exception as exc:
        # Never echo raw broker/network exceptions (may include account information).
        if archive and args.command == 'run':
            from src.data.shioaji_history import HistoryAPIError
            if isinstance(exc, HistoryAPIError) and not archive.meta('halt'):
                archive.set_meta('halt', {'job': None, 'status': 'session_error', 'detail': str(exc)})
        report = {'error_type': type(exc).__name__, 'message': 'No automatic retry; inspect local configuration and status.'}
        exit_code = 1
    finally:
        if archive:
            archive.close()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return exit_code


if __name__ == '__main__':
    sys.exit(main())
