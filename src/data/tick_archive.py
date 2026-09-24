"""Conservative, resumable historical equity tick archive (no broker imports)."""

from __future__ import annotations

import gzip
import hashlib
import json
import math
import os
import shutil
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, time as wall_time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

TAIPEI = ZoneInfo('Asia/Taipei')
MIB = 1024 ** 2
FIELDS = ('ts', 'close', 'volume', 'bid_price', 'bid_volume', 'ask_price', 'ask_volume', 'tick_type')


class ArchiveStop(RuntimeError):
    """Expected stop; never retry inside the worker."""


@dataclass(frozen=True)
class Policy:
    interval: float = 5.0
    daily_requests: int = 1000
    daily_bytes: int = 200 * MIB
    quota_fraction: float = 0.5
    reserve_bytes: int = 100 * MIB
    min_disk_bytes: int = 5 * 1024 ** 3

    def __post_init__(self):
        if not math.isfinite(self.interval) or self.interval < 5:
            raise ValueError('interval must be at least 5 seconds')
        if not 1 <= self.daily_requests <= 1000:
            raise ValueError('daily_requests must be 1..1000')
        if self.daily_bytes <= 0 or self.reserve_bytes < 100 * MIB:
            raise ValueError('positive budget and at least 100 MiB reserve required')
        if not 0 < self.quota_fraction <= 0.5:
            raise ValueError('quota_fraction must be in (0, 0.5]')
        if self.min_disk_bytes < 1024 ** 3:
            raise ValueError('keep at least 1 GiB free disk space')


class Calendar:
    def __init__(self, path: Path):
        payload = json.loads(path.read_text())
        self.year = payload['year']
        self.closed = {date.fromisoformat(d) for d in payload['closed_dates']}

    def is_open(self, day: date) -> bool:
        if day.year != self.year:
            raise ValueError(f'calendar only covers {self.year}; update it before continuing')
        return day.weekday() < 5 and day not in self.closed

    def days(self, start: date, end: date):
        if start > end:
            raise ValueError('start must not be after end')
        day = start
        while day <= end:
            if self.is_open(day):
                yield day
            day += timedelta(days=1)

    def quota_period(self, now: datetime) -> str:
        local = now.astimezone(TAIPEI)
        day = local.date()
        if local.time() < wall_time(8):
            day -= timedelta(days=1)
        while not self.is_open(day):
            day -= timedelta(days=1)
        return day.isoformat()


def check_window(now: datetime) -> None:
    # Apply even on holidays: no guesses about exceptional exchange sessions.
    if now.tzinfo is None:
        raise ValueError('clock must be timezone aware')
    if wall_time(8) <= now.astimezone(TAIPEI).time() < wall_time(16):
        raise ArchiveStop('outside download window: use 16:00–08:00 Asia/Taipei')


def check_external_volume(path: Path) -> None:
    """Do not recreate a missing macOS external volume on the internal drive."""
    absolute = path.absolute()
    if absolute.drive and not Path(absolute.anchor).exists():
        raise ArchiveStop(f'output drive is not available: {absolute.anchor}')
    if len(absolute.parts) >= 3 and absolute.parts[:2] == ('/', 'Volumes'):
        mount = Path(*absolute.parts[:3])
        if not mount.is_mount():
            raise ArchiveStop(f'external volume is not mounted: {mount}')


def validate_ticks(data: dict, day: str) -> int:
    if not all(k in data for k in FIELDS):
        raise ValueError('missing tick columns')
    size = len(data['ts'])
    if any(not isinstance(v, list) or len(v) != size for v in data.values()):
        raise ValueError('tick columns must be equally sized arrays')
    previous = 0
    expected = date.fromisoformat(day)
    for stamp in data['ts']:
        if not isinstance(stamp, int) or isinstance(stamp, bool) or stamp < previous:
            raise ValueError('invalid or out-of-order nanosecond timestamps')
        # Shioaji encodes Taiwan wall-clock values; never add eight hours.
        if datetime.fromtimestamp(stamp // 1_000_000_000, timezone.utc).date() != expected:
            raise ValueError('tick timestamps do not match requested date')
        previous = stamp
    return size


@contextmanager
def single_worker(path: Path):
    """A process lock shared by this project's CLI commands, released on crash."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as handle:
        if os.name == 'nt':
            import msvcrt
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b'0')
                handle.flush()
            def acquire():
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            def release():
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            def acquire():
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            def release():
                fcntl.flock(handle, fcntl.LOCK_UN)
        try:
            acquire()
        except OSError:
            raise ArchiveStop('another archive worker is running') from None
        try:
            yield
        finally:
            release()


class Archive:
    def __init__(self, root: Path):
        check_external_volume(root)
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.root / 'manifest.sqlite3')
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS jobs (
                exchange TEXT, code TEXT, day TEXT, status TEXT DEFAULT 'pending',
                rows INTEGER, path TEXT, sha256 TEXT, size INTEGER, detail TEXT,
                PRIMARY KEY (exchange, code, day));
            CREATE TABLE IF NOT EXISTS ledger (
                period TEXT PRIMARY KEY, requests INTEGER DEFAULT 0,
                bytes INTEGER DEFAULT 0, largest INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
            CREATE INDEX IF NOT EXISTS job_status ON jobs(status, day, exchange, code);
        ''')

    def close(self):
        self.db.close()

    def meta(self, key: str):
        row = self.db.execute('SELECT value FROM meta WHERE key=?', (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def set_meta(self, key, value):
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO meta VALUES (?,?)', (key, json.dumps(value)))

    def plan(self, universe: list[dict], calendar: Calendar, start: date, end: date):
        if start > end or end > datetime.now(TAIPEI).date():
            raise ValueError('invalid date range or future end date')
        days = list(calendar.days(start, end))
        signature = {'start': start.isoformat(), 'end': end.isoformat(),
                     'symbols': sorted([s['exchange'], s['code']] for s in universe)}
        previous = self.meta('plan_signature')
        if previous and previous != signature:
            raise ArchiveStop('archive plan is fixed; use a different output directory for a different scope')
        with self.db:
            for stock in universe:
                if stock['exchange'] not in ('TSE', 'OTC') or not stock['code'].isalnum():
                    raise ValueError('invalid exchange or code')
                listed = date.fromisoformat(stock['listed_on'])
                self.db.executemany('INSERT INTO jobs(exchange,code,day,status) VALUES (?,?,?,?) '
                                    'ON CONFLICT(exchange,code,day) DO UPDATE SET status=excluded.status '
                                    'WHERE jobs.status="listing_history_unverified" AND excluded.status="pending"',
                                    ((stock['exchange'], stock['code'], d.isoformat(),
                                      'pending' if d >= listed else 'listing_history_unverified') for d in days))
        self.set_meta('plan_signature', signature)
        self.set_meta('plan', {'start': start.isoformat(), 'end': end.isoformat(),
                              'trading_days': len(days), 'stocks': len(universe),
                              'universe_scope': 'current listed securities, not a point-in-time historical universe'})

    def summary(self):
        counts = dict(self.db.execute('SELECT status,COUNT(*) FROM jobs GROUP BY status').fetchall())
        total = self.db.execute('SELECT COALESCE(SUM(rows),0),COALESCE(SUM(size),0) FROM jobs WHERE status="done"').fetchone()
        return {'jobs': counts, 'stored_ticks': total[0], 'compressed_bytes': total[1],
                'halt': self.meta('halt'), 'plan': self.meta('plan'),
                'ledger': [dict(r) for r in self.db.execute('SELECT * FROM ledger ORDER BY period')]}

    def key(self, job):
        return (job['exchange'], job['code'], job['day'])

    def path(self, job):
        return self.root / 'ticks' / job['day'] / job['exchange'] / (job['code'] + '.json.gz')

    def record_done(self, job, path, rows):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        with self.db:
            self.db.execute('UPDATE jobs SET status="done",rows=?,path=?,sha256=?,size=?,detail=NULL '
                            'WHERE exchange=? AND code=? AND day=?',
                            (rows, str(path.relative_to(self.root)), digest, path.stat().st_size, *self.key(job)))

    def recover(self, job) -> bool:
        path = self.path(job)
        if not path.exists():
            return False
        try:
            with gzip.open(path, 'rt') as handle:
                payload = json.load(handle)
            if tuple(payload[k] for k in ('exchange', 'code', 'date')) != self.key(job):
                raise ValueError('archive identity mismatch')
            rows = validate_ticks(payload['data'], job['day'])
            if not rows:
                raise ValueError('empty archive')
            self.record_done(job, path, rows)
            return True
        except Exception:
            self.halt(job, 'corrupt_cache', 'existing archive failed validation; inspect locally')
            raise ArchiveStop('existing archive is invalid; stopped without re-downloading') from None

    def save(self, job, data, sdk_version):
        check_external_volume(self.root)
        rows = validate_ticks(data, job['day'])
        if not rows:
            raise ValueError('cannot mark an empty response complete')
        path = self.path(job)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix('.partial')
        payload = {'schema': 1, 'source': 'Shioaji ticks AllDay', 'sdk_version': sdk_version,
                   'exchange': job['exchange'], 'code': job['code'], 'date': job['day'],
                   'timestamp_encoding': 'int64 ns, Taiwan wall-clock (do not add 8h)',
                   'downloaded_at': datetime.now(TAIPEI).isoformat(), 'data': data}
        with temporary.open('wb') as raw:
            with gzip.GzipFile(fileobj=raw, mode='wb', mtime=0) as compressed:
                compressed.write(json.dumps(payload, ensure_ascii=False, allow_nan=False,
                                            separators=(',', ':')).encode())
            raw.flush()
            os.fsync(raw.fileno())
        os.replace(temporary, path)
        self.record_done(job, path, rows)

    def halt(self, job, status, detail):
        with self.db:
            self.db.execute('UPDATE jobs SET status=?,detail=? WHERE exchange=? AND code=? AND day=?',
                            (status, detail, *self.key(job)))
        self.set_meta('halt', {'job': list(self.key(job)), 'status': status, 'detail': detail})

    def clear_halt(self, reason: str, retry: bool):
        if not reason.strip():
            raise ValueError('a diagnosis is required')
        halted = self.meta('halt')
        if halted and halted.get('job') and retry:
            with self.db:
                self.db.execute('UPDATE jobs SET status="pending",detail=? WHERE exchange=? AND code=? AND day=? AND status!="done"',
                                ('manual retry: ' + reason, *halted['job']))
        # If a request's final usage is unknown, conservatively exhaust the old
        # local byte budget; a restart/manual review must not erase consumption.
        unsettled = self.meta('unsettled_request')
        if unsettled:
            with self.db:
                self.db.execute('UPDATE ledger SET bytes=MAX(bytes,?) WHERE period=?',
                                (unsettled['daily_bytes'], unsettled['period']))
            self.set_meta('unsettled_request', None)
        self.set_meta('last_manual_review', {'reason': reason, 'retry': retry, 'halt': halted})
        self.set_meta('halt', None)

    def verify(self):
        checked = 0
        for job in self.db.execute('SELECT * FROM jobs WHERE status="done"'):
            path = self.root / job['path']
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != job['sha256']:
                raise ArchiveStop(f'archive checksum failed: {job["exchange"]}/{job["code"]}/{job["day"]}')
            checked += 1
        return checked


class Downloader:
    def __init__(self, archive, api, calendar, policy=None, now=None, sleep=time.sleep):
        self.archive, self.api, self.calendar = archive, api, calendar
        self.policy = policy or Policy()
        self.now = now or (lambda: datetime.now(TAIPEI))
        self.sleep = sleep

    def usage(self):
        usage = self.api.usage()
        if any(not isinstance(usage.get(k), int) or usage[k] < 0
               for k in ('bytes', 'limit_bytes', 'remaining_bytes', 'connections')) or usage['limit_bytes'] <= 0:
            raise ArchiveStop('invalid usage response; no tick request sent')
        self.archive.set_meta('last_usage', usage)
        return usage

    def budget(self, period, usage):
        p = self.policy
        with self.archive.db:
            self.archive.db.execute('INSERT OR IGNORE INTO ledger(period) VALUES (?)', (period,))
        ledger = self.archive.db.execute('SELECT * FROM ledger WHERE period=?', (period,)).fetchone()
        # Entire-account ceiling includes other applications; a single response size is unknown.
        headroom = max(p.reserve_bytes, ledger['largest'] * 2)
        if usage['bytes'] + headroom >= int(usage['limit_bytes'] * p.quota_fraction):
            raise ArchiveStop('account traffic safety ceiling reached')
        if usage['remaining_bytes'] <= headroom:
            raise ArchiveStop('insufficient account traffic reserve')
        if ledger['requests'] >= p.daily_requests:
            raise ArchiveStop('archive request budget reached for this quota period')
        if ledger['bytes'] + max(MIB, ledger['largest'] * 2) >= p.daily_bytes:
            raise ArchiveStop('archive traffic budget reached for this quota period')
        if shutil.disk_usage(self.archive.root).free < max(p.min_disk_bytes, headroom * 2):
            raise ArchiveStop('disk reserve reached')

    def run(self, max_requests=1000):
        if self.archive.meta('halt'):
            raise ArchiveStop('previous error needs diagnosis; use clear-halt explicitly')
        for job in self.archive.db.execute('SELECT * FROM jobs WHERE status="in_flight"').fetchall():
            if not self.archive.recover(job):
                self.archive.halt(job, 'interrupted', 'process ended during a request; response/traffic is unknown')
                raise ArchiveStop('interrupted request needs review before retrying')
        if self.archive.meta('unsettled_request'):
            unsettled = self.archive.meta('unsettled_request')
            self.archive.set_meta('halt', {'job': unsettled['job'], 'status': 'accounting_unknown',
                                          'detail': 'saved data has unreconciled traffic usage'})
            raise ArchiveStop('previous request traffic is unknown; review before continuing')
        count = 0
        jobs = self.archive.db.execute('SELECT * FROM jobs WHERE status="pending" ORDER BY day,exchange,code')
        for job in jobs:
            if count >= max_requests:
                return count
            check_external_volume(self.archive.root)
            if self.archive.recover(job):
                continue
            check_window(self.now())
            local = self.now().astimezone(TAIPEI)
            if job['day'] > local.date().isoformat() or (job['day'] == local.date().isoformat() and local.hour < 16):
                raise ArchiveStop('requested trading day is not complete yet')
            previous_request = self.archive.meta('last_request_at')
            if previous_request is not None:
                delay = min(self.policy.interval, max(0, self.policy.interval - (self.now().timestamp() - previous_request)))
                if delay:
                    self.sleep(delay)
            # Re-check AFTER waiting, so a worker cannot cross into the market session.
            check_window(self.now())
            period = self.calendar.quota_period(self.now())
            try:
                before = self.usage()
                self.budget(period, before)
                contract = self.api.resolve(job['exchange'], job['code'])
                if contract is None:
                    self.archive.halt(job, 'unavailable', 'contract not available in current Shioaji universe')
                    raise ArchiveStop('contract unavailable; historical coverage requires review')
                # Contract initialization can consume time/traffic too. Recheck
                # immediately before the first historical request.
                check_window(self.now())
                before = self.usage()
                self.budget(period, before)
                check_window(self.now())
                period = self.calendar.quota_period(self.now())
                with self.archive.db:
                    self.archive.db.execute('UPDATE ledger SET requests=requests+1 WHERE period=?', (period,))
                    self.archive.db.execute('UPDATE jobs SET status="in_flight" WHERE exchange=? AND code=? AND day=?',
                                            self.archive.key(job))
                    self.archive.db.execute('INSERT OR REPLACE INTO meta VALUES (?,?)',
                                            ('last_request_at', json.dumps(self.now().timestamp())))
                    self.archive.db.execute('INSERT OR REPLACE INTO meta VALUES (?,?)',
                                            ('unsettled_request', json.dumps({'job': list(self.archive.key(job)),
                                                                            'period': period, 'daily_bytes': self.policy.daily_bytes})))
                count += 1
                data = self.api.ticks(contract, job['day'])
                if not data:
                    data = {field: [] for field in FIELDS}
                rows = validate_ticks(data, job['day'])
                # Persist returned data before another network call can fail.
                if rows:
                    self.archive.save(job, data, self.api.version)
                after = self.usage()
                delta = max(0, after['bytes'] - before['bytes'])
                with self.archive.db:
                    self.archive.db.execute('UPDATE ledger SET bytes=bytes+?,largest=MAX(largest,?) WHERE period=?',
                                            (delta, delta, period))
                    self.archive.db.execute('DELETE FROM meta WHERE key="unsettled_request"')
                if not rows:
                    self.archive.halt(job, 'empty_unverified', 'empty response; inspect quota, trading calendar and suspension/listing history')
                    raise ArchiveStop('empty response is not proof of zero trades; review before continuing')
                self.budget(period, after)
            except ArchiveStop:
                if self.archive.meta('unsettled_request') and not self.archive.meta('halt'):
                    self.archive.set_meta('halt', {'job': list(self.archive.key(job)), 'status': 'accounting_unknown',
                                                   'detail': 'request usage could not be confirmed'})
                raise
            except Exception as exc:
                # SDK exception strings may contain secrets or account identifiers.
                self.archive.set_meta('halt', {'job': list(self.archive.key(job)), 'status': 'error',
                                               'detail': type(exc).__name__})
                with self.archive.db:
                    self.archive.db.execute('UPDATE jobs SET status="error",detail=? '
                                            'WHERE exchange=? AND code=? AND day=? AND status!="done"',
                                            (type(exc).__name__, *self.archive.key(job)))
                raise ArchiveStop(f'worker stopped on {type(exc).__name__}; no automatic retry') from None
        return count
