"""Offline safety and restart tests for the historical tick archiver."""

import gzip
import json
from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest

from src.data.tick_archive import (
    Archive,
    ArchiveStop,
    Calendar,
    Downloader,
    FIELDS,
    MIB,
    Policy,
    validate_ticks,
)


def tick_data(day="2026-09-23"):
    # Deliberately include duplicate nanosecond timestamps and values above 2**53.
    stamp = int(datetime.fromisoformat(day + "T09:00:00+00:00").timestamp()) * 10**9 + 123
    return {
        "ts": [stamp, stamp, stamp + 1],
        "close": [100.0, 100.5, 100.5],
        "volume": [1, 2, 3],
        "bid_price": [99.5, 100.0, 100.0],
        "bid_volume": [10, 20, 30],
        "ask_price": [100.0, 100.5, 100.5],
        "ask_volume": [30, 20, 10],
        "tick_type": [1, 2, 1],
    }


class FakeAPI:
    version = "test-offline"

    def __init__(self, *, response=None, error=None, used=0, remaining=None, increment=1024):
        self.response = response
        self.error = error
        self.used = used
        self.limit = 500 * MIB
        self.remaining = remaining
        self.increment = increment
        self.events = []

    def usage(self):
        self.events.append("usage")
        return {
            "connections": 1,
            "bytes": self.used,
            "limit_bytes": self.limit,
            "remaining_bytes": self.limit - self.used if self.remaining is None else self.remaining,
        }

    def resolve(self, exchange, code):
        self.events.append(("resolve", exchange, code))
        return (exchange, code)

    def ticks(self, contract, day):
        self.events.append(("ticks", contract, day))
        if self.error:
            raise self.error
        self.used += self.increment
        return tick_data(day) if self.response is None else self.response

    @property
    def requests(self):
        return [event for event in self.events if isinstance(event, tuple) and event[0] == "ticks"]


class Clock:
    def __init__(self, value="2026-09-24T16:00:00+08:00"):
        self.value = datetime.fromisoformat(value)
        self.sleeps = []

    def now(self):
        return self.value

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.value += timedelta(seconds=seconds)


@pytest.fixture
def calendar(tmp_path):
    path = tmp_path / "calendar.json"
    path.write_text(json.dumps({"year": 2026, "closed_dates": ["2026-09-25", "2026-09-28"]}))
    return Calendar(path)


@pytest.fixture
def archive(tmp_path, monkeypatch):
    monkeypatch.setattr("src.data.tick_archive.shutil.disk_usage", lambda _: SimpleNamespace(free=20 * 1024**3))
    result = Archive(tmp_path / "archive")
    yield result
    result.close()


def add_jobs(archive, *codes, day="2026-09-23"):
    with archive.db:
        archive.db.executemany(
            "INSERT INTO jobs(exchange,code,day) VALUES ('TSE',?,?)", [(code, day) for code in codes]
        )


def job(archive, code="2330"):
    return archive.db.execute("SELECT * FROM jobs WHERE code=?", (code,)).fetchone()


def downloader(archive, calendar, api=None, clock=None, policy=None):
    api = api or FakeAPI()
    clock = clock or Clock()
    return Downloader(archive, api, calendar, policy=policy, now=clock.now, sleep=clock.sleep)


@pytest.mark.parametrize("hour", [8, 9, 12, 15])
def test_market_window_never_calls_broker(archive, calendar, hour):
    add_jobs(archive, "2330")
    worker = downloader(archive, calendar, clock=Clock(f"2026-09-24T{hour:02d}:00:00+08:00"))

    with pytest.raises(ArchiveStop, match="outside download window"):
        worker.run()

    assert worker.api.events == []
    assert job(archive)["status"] == "pending"


def test_market_window_checked_again_after_wait(archive, calendar):
    add_jobs(archive, "2330", "2454")
    clock = Clock("2026-09-24T07:59:58+08:00")
    worker = downloader(archive, calendar, clock=clock)

    with pytest.raises(ArchiveStop, match="outside download window"):
        worker.run()

    assert len(worker.api.requests) == 1
    assert clock.sleeps == [5.0]
    assert job(archive, "2454")["status"] == "pending"
    assert archive.summary()["ledger"][0]["period"] == "2026-09-23"


@pytest.mark.parametrize("clock_value,day", [
    ("2026-09-24T07:00:00+08:00", "2026-09-24"),
    ("2026-09-24T16:00:00+08:00", "2026-09-29"),
])
def test_incomplete_or_future_day_stays_pending(archive, calendar, clock_value, day):
    add_jobs(archive, "2330", day=day)
    worker = downloader(archive, calendar, clock=Clock(clock_value))

    with pytest.raises(ArchiveStop, match="not complete yet"):
        worker.run()

    assert worker.api.events == []
    assert job(archive)["status"] == "pending"


def test_today_is_available_after_download_window_opens(archive, calendar):
    add_jobs(archive, "2330", day="2026-09-24")
    worker = downloader(archive, calendar)

    assert worker.run() == 1
    assert job(archive)["status"] == "done"


@pytest.mark.parametrize("used,remaining,message", [
    (150 * MIB, None, "account traffic safety ceiling"),
    (0, 100 * MIB, "account traffic reserve"),
])
def test_account_wide_usage_blocks_before_tick_query(archive, calendar, used, remaining, message):
    add_jobs(archive, "2330")
    worker = downloader(archive, calendar, api=FakeAPI(used=used, remaining=remaining))

    with pytest.raises(ArchiveStop, match=message):
        worker.run()

    assert worker.api.events == ["usage"]
    assert archive.summary()["ledger"][0]["requests"] == 0


def test_request_budget_survives_new_archive_and_worker(archive, calendar):
    add_jobs(archive, "2330", "2454")
    policy = Policy(daily_requests=1)
    worker = downloader(archive, calendar, policy=policy)
    with pytest.raises(ArchiveStop, match="request budget"):
        worker.run()
    assert len(worker.api.requests) == 1

    reopened = Archive(archive.root)
    try:
        second = downloader(reopened, calendar, policy=policy)
        with pytest.raises(ArchiveStop, match="request budget"):
            second.run()
        assert second.api.requests == []
        assert reopened.summary()["ledger"][0]["requests"] == 1
        assert job(reopened, "2454")["status"] == "pending"
    finally:
        reopened.close()


def test_daily_bytes_stop_without_fetching_next_stock(archive, calendar):
    add_jobs(archive, "2330", "2454")
    worker = downloader(archive, calendar, api=FakeAPI(increment=2 * MIB), policy=Policy(daily_bytes=3 * MIB))

    with pytest.raises(ArchiveStop, match="archive traffic budget"):
        worker.run()

    assert len(worker.api.requests) == 1
    assert archive.summary()["ledger"][0]["bytes"] == 2 * MIB
    assert job(archive)["status"] == "done"
    assert job(archive, "2454")["status"] == "pending"


def test_low_disk_reserve_prevents_request(archive, calendar, monkeypatch):
    add_jobs(archive, "2330")
    monkeypatch.setattr("src.data.tick_archive.shutil.disk_usage", lambda _: SimpleNamespace(free=4 * 1024**3))
    worker = downloader(archive, calendar)

    with pytest.raises(ArchiveStop, match="disk reserve"):
        worker.run()

    assert worker.api.requests == []


def test_exception_is_persisted_without_secret_or_automatic_retry(archive, calendar):
    add_jobs(archive, "2330", "2454")
    worker = downloader(archive, calendar, api=FakeAPI(error=RuntimeError("SECRET_ACCOUNT_TOKEN")))

    with pytest.raises(ArchiveStop, match="no automatic retry") as error:
        worker.run()
    assert "SECRET_ACCOUNT_TOKEN" not in str(error.value)
    assert "SECRET_ACCOUNT_TOKEN" not in json.dumps(archive.summary())
    assert job(archive)["status"] == "error"
    assert archive.summary()["ledger"][0]["requests"] == 1

    events = list(worker.api.events)
    with pytest.raises(ArchiveStop, match="previous error needs diagnosis"):
        worker.run()
    assert worker.api.events == events
    assert len(worker.api.requests) == 1
    assert job(archive, "2454")["status"] == "pending"


@pytest.mark.parametrize("response", [{field: [] for field in FIELDS}, {}])
def test_empty_ticks_check_usage_and_require_review(archive, calendar, response):
    add_jobs(archive, "2330", "2454")
    worker = downloader(archive, calendar, api=FakeAPI(response=response))

    with pytest.raises(ArchiveStop, match="empty response"):
        worker.run()

    assert worker.api.events[-1] == "usage"
    request_index = worker.api.events.index(worker.api.requests[0])
    assert "usage" in worker.api.events[request_index + 1:]
    assert len(worker.api.requests) == 1
    assert job(archive)["status"] == "empty_unverified"
    assert not archive.path(job(archive)).exists()
    with pytest.raises(ArchiveStop, match="previous error needs diagnosis"):
        worker.run()
    assert len(worker.api.requests) == 1


def test_contract_initialization_traffic_is_checked_before_ticks(archive, calendar):
    add_jobs(archive, "2330")

    class ContractAPI(FakeAPI):
        def resolve(self, exchange, code):
            contract = super().resolve(exchange, code)
            self.used += 150 * MIB
            return contract

    worker = downloader(archive, calendar, api=ContractAPI())
    with pytest.raises(ArchiveStop, match="account traffic safety ceiling"):
        worker.run()
    assert worker.api.requests == []
    assert job(archive)["status"] == "pending"


def test_contract_initialization_cannot_cross_into_session(archive, calendar):
    add_jobs(archive, "2330")
    clock = Clock("2026-09-24T07:59:58+08:00")

    class SlowContractAPI(FakeAPI):
        def resolve(self, exchange, code):
            clock.value += timedelta(seconds=3)
            return super().resolve(exchange, code)

    worker = downloader(archive, calendar, api=SlowContractAPI(), clock=clock)
    with pytest.raises(ArchiveStop, match="outside download window"):
        worker.run()
    assert worker.api.requests == []


def test_final_usage_check_cannot_cross_into_session(archive, calendar):
    add_jobs(archive, "2330")
    clock = Clock("2026-09-24T07:59:59+08:00")

    class SlowFinalUsageAPI(FakeAPI):
        def usage(self):
            result = super().usage()
            if any(isinstance(event, tuple) and event[0] == "resolve" for event in self.events):
                clock.value += timedelta(seconds=2)
            return result

    worker = downloader(archive, calendar, api=SlowFinalUsageAPI(), clock=clock)
    with pytest.raises(ArchiveStop, match="outside download window"):
        worker.run()

    assert worker.api.requests == []
    assert job(archive)["status"] == "pending"
    assert archive.summary()["ledger"][0]["requests"] == 0


def test_saved_ticks_survive_post_request_usage_failure(archive, calendar):
    add_jobs(archive, "2330", "2454")

    class FailingUsageAPI(FakeAPI):
        def usage(self):
            if self.requests:
                raise RuntimeError("usage unavailable")
            return super().usage()

    worker = downloader(archive, calendar, api=FailingUsageAPI())
    with pytest.raises(ArchiveStop, match="no automatic retry"):
        worker.run()

    assert job(archive)["status"] == "done"
    assert job(archive, "2454")["status"] == "pending"
    assert archive.verify() == 1
    with pytest.raises(ArchiveStop, match="previous error needs diagnosis"):
        worker.run()
    assert len(worker.api.requests) == 1


@pytest.mark.parametrize("saved_response", [False, True])
def test_crash_review_preserves_unknown_usage_budget_across_restarts(archive, calendar, saved_response):
    add_jobs(archive, "2330", "2454")
    policy = Policy(daily_bytes=10 * MIB)

    class CrashingUsageAPI(FakeAPI):
        def usage(self):
            if self.requests:
                raise KeyboardInterrupt()
            return super().usage()

    api = CrashingUsageAPI() if saved_response else FakeAPI(error=KeyboardInterrupt())
    first = downloader(archive, calendar, api=api, policy=policy)
    with pytest.raises(KeyboardInterrupt):
        first.run()
    if api.error:
        api.error.__traceback__ = None  # Release the fake's saved exception/cursor like process exit.
    archive.close()  # A terminated process releases its SQLite connection and cursors.

    reopened = Archive(archive.root)
    try:
        restarted = downloader(reopened, calendar, policy=policy)
        with pytest.raises(ArchiveStop, match="review"):
            restarted.run()
        assert restarted.api.events == []

        reopened.clear_halt("Reviewed interrupted request; leave its unknown traffic reserved.", retry=True)
        if saved_response:
            # Reviewing accounting must not turn a valid completed file into a retry.
            assert job(reopened)["status"] == "done"
            assert reopened.verify() == 1
        else:
            assert job(reopened)["status"] == "pending"

        same_period = downloader(reopened, calendar, policy=policy)
        with pytest.raises(ArchiveStop, match="archive traffic budget"):
            same_period.run()
        assert same_period.api.requests == []
        old_ledger = reopened.summary()["ledger"][0]
        assert old_ledger["requests"] == 1
        assert old_ledger["bytes"] >= policy.daily_bytes

        next_period = downloader(
            reopened, calendar, policy=policy, clock=Clock("2026-09-29T16:00:00+08:00")
        )
        assert next_period.run() == (1 if saved_response else 2)
        requested_codes = [request[1][1] for request in next_period.api.requests]
        assert requested_codes == (["2454"] if saved_response else ["2330", "2454"])
        assert reopened.verify() == 2
        assert reopened.summary()["ledger"][0] == old_ledger
    finally:
        reopened.close()


def test_restart_retains_minimum_spacing_between_tick_requests(archive, calendar):
    add_jobs(archive, "2330", "2454")
    first_clock = Clock()
    first = downloader(archive, calendar, clock=first_clock)
    assert first.run(max_requests=1) == 1

    reopened = Archive(archive.root)
    try:
        next_clock = Clock("2026-09-24T16:00:02+08:00")

        class TimestampAPI(FakeAPI):
            def ticks(self, contract, day):
                self.requested_at = next_clock.now()
                return super().ticks(contract, day)

        api = TimestampAPI()
        second = downloader(reopened, calendar, api=api, clock=next_clock)
        assert second.run() == 1
        assert (api.requested_at - first_clock.now()).total_seconds() >= 5
        assert next_clock.sleeps == [3.0]
    finally:
        reopened.close()


def test_restart_spacing_cannot_push_request_into_session(archive, calendar):
    add_jobs(archive, "2330", "2454")
    first = downloader(archive, calendar, clock=Clock("2026-09-24T07:59:58+08:00"))
    assert first.run(max_requests=1) == 1

    second_clock = Clock("2026-09-24T07:59:59+08:00")
    second = downloader(archive, calendar, clock=second_clock)
    with pytest.raises(ArchiveStop, match="outside download window"):
        second.run()

    assert second.api.events == []
    assert second_clock.sleeps == [4.0]
    assert job(archive, "2454")["status"] == "pending"


def test_completed_job_is_not_fetched_twice(archive, calendar):
    add_jobs(archive, "2330")
    worker = downloader(archive, calendar)

    assert worker.run() == 1
    assert worker.run() == 0
    assert len(worker.api.requests) == 1
    assert archive.verify() == 1


@pytest.mark.parametrize("status", ["pending", "in_flight"])
def test_file_written_before_manifest_commit_is_recovered_without_network(archive, calendar, status):
    add_jobs(archive, "2330")
    archive.save(job(archive), tick_data(), "test-offline")
    with archive.db:
        archive.db.execute("UPDATE jobs SET status=?,rows=NULL,path=NULL,sha256=NULL,size=NULL", (status,))
    worker = downloader(archive, calendar)

    assert worker.run() == 0
    assert worker.api.events == []
    assert job(archive)["status"] == "done"
    assert archive.verify() == 1


def test_process_interruption_preserves_request_count_and_never_retries(archive, calendar):
    add_jobs(archive, "2330", "2454")
    worker = downloader(archive, calendar, api=FakeAPI(error=KeyboardInterrupt()))

    # BaseException simulates a process stopping before ordinary error handling.
    with pytest.raises(KeyboardInterrupt):
        worker.run()
    assert job(archive)["status"] == "in_flight"
    assert archive.summary()["ledger"][0]["requests"] == 1
    assert not archive.path(job(archive)).exists()

    restarted = downloader(archive, calendar)
    with pytest.raises(ArchiveStop, match="interrupted request needs review"):
        restarted.run()

    assert restarted.api.events == []
    assert job(archive)["status"] == "interrupted"
    assert job(archive, "2454")["status"] == "pending"
    assert archive.meta("halt")["status"] == "interrupted"
    assert archive.summary()["ledger"][0]["requests"] == 1


def test_nanoseconds_and_duplicate_timestamp_rows_round_trip_exactly(archive, calendar):
    add_jobs(archive, "2330")
    data = tick_data()
    worker = downloader(archive, calendar, api=FakeAPI(response=data))
    worker.run()

    with gzip.open(archive.path(job(archive)), "rt") as handle:
        stored = json.load(handle)

    assert stored["data"] == data
    assert stored["data"]["ts"][0] > 2**53
    assert stored["data"]["ts"][0] == stored["data"]["ts"][1]
    assert stored["data"]["ts"][2] - stored["data"]["ts"][1] == 1
    assert job(archive)["rows"] == 3
    assert stored["timestamp_encoding"] == "int64 ns, Taiwan wall-clock (do not add 8h)"


@pytest.mark.parametrize("value,expected", [
    ("2026-09-24T07:59:59+08:00", "2026-09-23"),
    ("2026-09-24T08:00:00+08:00", "2026-09-24"),
    ("2026-09-25T17:00:00+08:00", "2026-09-24"),
    ("2026-09-26T17:00:00+08:00", "2026-09-24"),
    ("2026-09-28T17:00:00+08:00", "2026-09-24"),
    ("2026-09-29T07:59:59+08:00", "2026-09-24"),
    ("2026-09-29T08:00:00+08:00", "2026-09-29"),
    ("2026-09-29T00:00:00+00:00", "2026-09-29"),
])
def test_quota_reset_uses_only_open_days_at_8am(calendar, value, expected):
    assert calendar.quota_period(datetime.fromisoformat(value)) == expected


def test_calendar_excludes_holidays_and_weekends(calendar):
    assert list(calendar.days(date(2026, 9, 24), date(2026, 9, 29))) == [date(2026, 9, 24), date(2026, 9, 29)]


@pytest.mark.parametrize("change", ["symbols", "start", "end"])
def test_replanning_cannot_silently_change_archive_scope(archive, calendar, change):
    universe = [{"exchange": "TSE", "code": "2330", "listed_on": "1994-09-05"}]
    start, end = date(2026, 9, 21), date(2026, 9, 23)
    archive.plan(universe, calendar, start, end)
    original_summary = archive.summary()

    if change == "symbols":
        universe.append({"exchange": "TSE", "code": "2454", "listed_on": "2001-07-23"})
    elif change == "start":
        start = date(2026, 9, 22)
    else:
        end = date(2026, 9, 22)

    with pytest.raises(ArchiveStop, match="different output directory"):
        archive.plan(universe, calendar, start, end)

    assert archive.summary() == original_summary
    assert archive.db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 3


def test_verified_earlier_listing_date_unlocks_gaps_and_preserves_done_files(archive, calendar):
    universe = [{"exchange": "TSE", "code": "2330", "listed_on": "2026-09-23"}]
    start, end = date(2026, 9, 21), date(2026, 9, 23)
    archive.plan(universe, calendar, start, end)
    assert archive.summary()["jobs"] == {"listing_history_unverified": 2, "pending": 1}
    completed = archive.db.execute("SELECT * FROM jobs WHERE day='2026-09-23'").fetchone()
    archive.save(completed, tick_data("2026-09-23"), "test-offline")
    original_file = archive.path(completed).read_bytes()

    universe[0]["listed_on"] = "2026-09-21"
    archive.plan(universe, calendar, start, end)
    archive.plan(universe, calendar, start, end)

    assert archive.summary()["jobs"] == {"done": 1, "pending": 2}
    assert archive.path(completed).read_bytes() == original_file
    worker = downloader(archive, calendar)
    assert worker.run() == 2
    assert [request[2] for request in worker.api.requests] == ["2026-09-21", "2026-09-22"]
    assert archive.verify() == 3


def test_verify_detects_modified_archive(archive):
    add_jobs(archive, "2330")
    archive.save(job(archive), tick_data(), "test-offline")
    path = archive.path(job(archive))
    path.write_bytes(path.read_bytes() + b"corruption")

    with pytest.raises(ArchiveStop, match="checksum failed"):
        archive.verify()


def test_invalid_crash_cache_stops_without_redownload(archive, calendar):
    add_jobs(archive, "2330")
    path = archive.path(job(archive))
    path.parent.mkdir(parents=True)
    path.write_bytes(b"corrupt cached data")
    worker = downloader(archive, calendar)

    with pytest.raises(ArchiveStop, match="without re-downloading"):
        worker.run()

    assert worker.api.events == []
    assert job(archive)["status"] == "corrupt_cache"
    assert archive.meta("halt")["status"] == "corrupt_cache"


def test_invalid_date_is_not_saved_as_success(archive, calendar):
    add_jobs(archive, "2330")
    worker = downloader(archive, calendar, api=FakeAPI(response=tick_data("2026-09-22")))

    with pytest.raises(ArchiveStop, match="ValueError"):
        worker.run()

    assert job(archive)["status"] == "error"
    assert not archive.path(job(archive)).exists()


@pytest.mark.parametrize("timestamp", [1.79e18, True])
def test_float_or_boolean_timestamps_are_rejected(timestamp):
    data = tick_data()
    data["ts"][0] = timestamp
    with pytest.raises(ValueError, match="timestamps"):
        validate_ticks(data, "2026-09-23")
