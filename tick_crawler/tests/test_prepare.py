"""Offline checks of the actual distributable migration snapshot."""

import json
import shutil
import sqlite3
import subprocess
import sys

import pytest

import prepare
from src.data.tick_archive import ArchiveStop, single_worker


def test_restore_snapshot_and_refuse_overwrite(tmp_path):
    output = tmp_path / 'external disk' / 'archive'
    result = prepare.restore(output)
    assert result['network_requests'] == 0
    assert result['jobs'] == {'pending': 281833, 'listing_history_unverified': 2999}
    db = sqlite3.connect(output / 'manifest.sqlite3')
    try:
        assert {r[0] for r in db.execute('SELECT key FROM meta')} == {
            'plan', 'plan_signature', 'universe_as_of'}
        assert db.execute('SELECT COUNT(*) FROM ledger').fetchone()[0] == 0
    finally:
        db.close()
    universe = json.loads((output / 'universe.json').read_text())
    assert len(universe['stocks']) == 1978
    with pytest.raises(ArchiveStop, match='already exists'):
        prepare.restore(output)


def test_modified_seed_refuses_restore(tmp_path, monkeypatch):
    kit = tmp_path / 'kit'
    manifest = prepare.verify_package()
    for relative in [*manifest['sha256'], 'PACKAGE.json']:
        target = kit / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(prepare.ROOT / relative, target)
    (kit / 'seed/manifest.sqlite3.gz').write_bytes(b'corrupt')
    monkeypatch.setattr(prepare, 'ROOT', kit)
    with pytest.raises(ArchiveStop, match='checksum mismatch'):
        prepare.restore(tmp_path / 'output')
    assert not (tmp_path / 'output').exists()


def test_worker_lock_blocks_other_process_and_releases(tmp_path):
    lock = tmp_path / 'worker.lock'
    code = ('from pathlib import Path; from src.data.tick_archive import single_worker; '
            'ctx = single_worker(Path(__import__("sys").argv[1])); ctx.__enter__(); ctx.__exit__(None,None,None)')
    def attempt():
        return subprocess.run([sys.executable, '-c', code, str(lock)],
                              cwd=prepare.ROOT, capture_output=True, text=True)
    with single_worker(lock):
        blocked = attempt()
        assert blocked.returncode != 0
        assert 'another archive worker is running' in blocked.stderr
    assert attempt().returncode == 0
