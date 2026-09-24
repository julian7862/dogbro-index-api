"""Opt-in, one-request real API integration test; never part of offline runs.

RUN_SHIOAJI_LIVE_TEST=1 venv/bin/python -m pytest tests/test_shioaji_live.py -s -o addopts=''
The daily receipt prevents an accidental repeat of a historical tick request.
"""

import gzip
import json
import os
import time
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from src.data.shioaji_history import HistoryAPIError, open_history_api
from src.data.tick_archive import Archive, Calendar, MIB, TAIPEI, single_worker, validate_ticks

PROJECT = Path(__file__).resolve().parents[1]


@pytest.mark.integration
@pytest.mark.skipif(os.getenv('RUN_SHIOAJI_LIVE_TEST') != '1', reason='explicit live API opt-in required')
def test_live_historical_ticks_and_archive(tmp_path):
    """Resolve a real contract, query once, store and reopen exact tick arrays."""
    day = '2026-03-02'
    today = datetime.now(TAIPEI)
    receipt = PROJECT / '.cache' / 'shioaji_live' / f'{today.date()}.json'
    receipt.parent.mkdir(parents=True, exist_ok=True)
    result = {'started_at': today.isoformat(), 'stock': '2330', 'date': day,
              'mode': 'simulation', 'tick_requests': 0, 'status': 'started'}
    archive = None
    started = time.monotonic()
    with single_worker(PROJECT / '.cache' / 'shioaji-history.lock'):
        if receipt.exists():
            pytest.skip('a live smoke-test receipt already exists for today; inspect it before another request')
        receipt.write_text(json.dumps(result))
        try:
            calendar = Calendar(PROJECT / 'data/reference/twse_holidays_2026.json')
            assert calendar.is_open(date.fromisoformat(day))
            archive = Archive(tmp_path / 'archive')
            archive.plan([{'exchange': 'TSE', 'code': '2330', 'listed_on': '1994-09-05'}],
                         calendar, date.fromisoformat(day), date.fromisoformat(day))
            job = archive.db.execute('SELECT * FROM jobs').fetchone()
            with open_history_api(PROJECT / '.env') as api:
                result['sdk_version'] = api.version
                before_login_data = api.usage()
                assert before_login_data['remaining_bytes'] > 100 * MIB
                assert before_login_data['bytes'] + 100 * MIB < before_login_data['limit_bytes'] // 2
                contract = api.resolve('TSE', '2330')
                assert contract is not None, '2330 contract was not returned'
                result['contract_resolved'] = True
                before = api.usage()
                result['usage_before_ticks'] = before
                assert before['remaining_bytes'] > 100 * MIB
                assert before['bytes'] + 100 * MIB < before['limit_bytes'] // 2
                result['tick_requests'] = 1
                receipt.write_text(json.dumps(result))  # Record before touching the network.
                data = api.ticks(contract, day)
                # Always inspect quota before interpreting an empty response.
                after = api.usage()
                result['usage_after_ticks'] = after
                result['observed_tick_bytes'] = max(0, after['bytes'] - before['bytes'])
                result['observed_session_bytes'] = max(0, after['bytes'] - before_login_data['bytes'])
                assert data, 'empty tick response; inspect usage in receipt; no retry'
                rows = validate_ticks(data, day)
                assert rows > 0, 'no ticks returned; no retry'
                archive.save(job, data, api.version)
                path = archive.path(job)
                result['rows'] = rows
                result['compressed_bytes'] = path.stat().st_size
                for label, stamp in [('first_tick', data['ts'][0]), ('last_tick', data['ts'][-1])]:
                    seconds, nanoseconds = divmod(stamp, 1_000_000_000)
                    result[label] = datetime.fromtimestamp(seconds, timezone.utc).strftime('%Y-%m-%d %H:%M:%S') + f'.{nanoseconds:09d}'
            result['logout_success'] = True
            assert archive.verify() == 1
            archive.close()
            archive = Archive(tmp_path / 'archive')
            assert archive.summary()['jobs'] == {'done': 1}
            with gzip.open(path, 'rt') as handle:
                persisted = json.load(handle)
            assert persisted['data'] == data  # Includes original ns integers and every returned column.
            assert archive.recover(job)
            result['archive_round_trip'] = True
            result['checksum_verified'] = True
            result['status'] = 'passed'
        except BaseException as error:
            result['status'] = 'failed'
            result['error_type'] = type(error).__name__
            if isinstance(error, HistoryAPIError):
                result['error'] = str(error)  # Already sanitized by the adapter.
            raise
        finally:
            if archive:
                archive.close()
            # Only tiny, non-secret verification metadata remains on the internal disk.
            # Real tick data lives in tmp_path and is removed even on assertion failure.
            if (tmp_path / 'archive').exists():
                import shutil
                shutil.rmtree(tmp_path / 'archive')
            result['elapsed_seconds'] = round(time.monotonic() - started, 2)
            result['temporary_tick_files_removed'] = not (tmp_path / 'archive').exists()
            receipt.write_text(json.dumps(result, ensure_ascii=False, indent=2))
            print(json.dumps(result, ensure_ascii=False, indent=2))
