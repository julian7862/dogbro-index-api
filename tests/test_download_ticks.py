from contextlib import contextmanager
from pathlib import Path

import pytest

import download_ticks as cli
from src.data.shioaji_history import HistoryAPIError
from src.data.tick_archive import Archive, ArchiveStop, check_external_volume


def prepared(tmp_path, monkeypatch):
    calendar = (cli.PROJECT / 'data/reference/twse_holidays_2026.json').read_text()
    monkeypatch.setattr(cli, 'PROJECT', tmp_path)
    reference = tmp_path / 'data/reference'
    reference.mkdir(parents=True)
    (reference / 'twse_holidays_2026.json').write_text(calendar)
    root = tmp_path / 'archive'
    archive = Archive(root)
    with archive.db:
        archive.db.execute('INSERT INTO jobs(exchange,code,day) VALUES ("TSE","2330","2026-03-02")')
    archive.close()
    return root


def test_intraday_cli_refuses_before_login(tmp_path, monkeypatch):
    root = prepared(tmp_path, monkeypatch)
    def blocked(now):
        raise ArchiveStop('market is open')
    monkeypatch.setattr(cli, 'check_window', blocked)
    def unexpected_login(*args):
        pytest.fail('must not login')
    monkeypatch.setattr('src.data.shioaji_history.open_history_api', unexpected_login)
    assert cli.main(['--output', str(root), 'run']) == 2


def test_login_failure_halts_later_runs_until_explicit_review(tmp_path, monkeypatch):
    root = prepared(tmp_path, monkeypatch)
    monkeypatch.setattr(cli, 'check_window', lambda now: None)
    attempts = []
    @contextmanager
    def failed_login(env):
        attempts.append(1)
        raise HistoryAPIError('Shioaji login failed (AuthError, status=401)')
        yield
    monkeypatch.setattr('src.data.shioaji_history.open_history_api', failed_login)
    assert cli.main(['--output', str(root), 'run']) == 1
    assert cli.main(['--output', str(root), 'run']) == 2
    assert attempts == [1]
    archive = Archive(root)
    assert archive.meta('halt')['status'] == 'session_error'
    archive.close()
    assert cli.main(['--output', str(root), 'clear-halt', '--reason', 'credentials corrected locally', '--retry-failed']) == 0


def test_unmounted_external_disk_is_rejected_before_directory_creation(monkeypatch):
    monkeypatch.setattr(Path, 'is_mount', lambda path: False)
    def must_not_create(*args, **kwargs):
        pytest.fail('must not create a fake external disk directory')
    monkeypatch.setattr(Path, 'mkdir', must_not_create)
    with pytest.raises(ArchiveStop, match='not mounted'):
        Archive(Path('/Volumes/TEST_NOT_ATTACHED/shioaji_ticks'))


def test_mounted_disk_and_regular_paths_are_allowed(monkeypatch):
    monkeypatch.setattr(Path, 'is_mount', lambda path: str(path) == '/Volumes/Tick Data')
    check_external_volume(Path('/Volumes/Tick Data/shioaji_ticks'))
    check_external_volume(Path('/tmp/local-test-archive'))
