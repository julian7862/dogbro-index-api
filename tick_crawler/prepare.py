"""Verify and restore the bundled progress snapshot without accessing the API."""

import argparse
import gzip
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
from pathlib import Path

from src.data.tick_archive import ArchiveStop, check_external_volume, single_worker

ROOT = Path(__file__).resolve().parent


def verify_package():
    expected = json.loads((ROOT / 'PACKAGE.json').read_text())
    for relative, digest in expected['sha256'].items():
        if hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() != digest:
            raise ArchiveStop(f'package checksum mismatch: {relative}')
    return expected


def restore(output):
    package = verify_package()
    check_external_volume(output)
    output = output.resolve()
    if output.exists():
        raise ArchiveStop('output already exists; keep it intact and choose a new directory, or use download_ticks.py status')
    output.parent.mkdir(parents=True, exist_ok=True)
    staged = Path(tempfile.mkdtemp(prefix=f'.{output.name}-restore-', dir=output.parent))
    try:
        with gzip.open(ROOT / 'seed/manifest.sqlite3.gz', 'rb') as source:
            with (staged / 'manifest.sqlite3').open('wb') as target:
                shutil.copyfileobj(source, target)
                target.flush()
                os.fsync(target.fileno())
        snapshot = json.loads((ROOT / 'seed/snapshot.json').read_text())
        database = staged / 'manifest.sqlite3'
        if hashlib.sha256(database.read_bytes()).hexdigest() != snapshot['database_sha256']:
            raise ArchiveStop('restored database checksum mismatch')
        with sqlite3.connect(database) as db:
            if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                raise ArchiveStop('restored SQLite integrity check failed')
            counts = dict(db.execute('SELECT status, COUNT(*) FROM jobs GROUP BY status').fetchall())
        db.close()
        if counts != snapshot['jobs']:
            raise ArchiveStop('restored job counts do not match the snapshot')
        shutil.copyfile(ROOT / 'seed/universe.json', staged / 'universe.json')
        check_external_volume(output)
        os.replace(staged, output)
        return {'status': 'ready', 'output': str(output), 'jobs': counts,
                'network_requests': 0, 'package_version': package['version']}
    finally:
        if staged.exists():
            shutil.rmtree(staged)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='new archive directory on your external drive')
    parser.add_argument('--verify-only', action='store_true', help='verify bundled files without restoring progress')
    args = parser.parse_args(argv)
    if not args.verify_only and args.output is None:
        parser.error('--output is required unless using --verify-only')
    try:
        with single_worker(ROOT / '.cache/shioaji-history.lock'):
            if args.verify_only:
                package = verify_package()
                result = {'status': 'verified', 'files': len(package['sha256']), 'version': package['version']}
            else:
                result = restore(args.output.expanduser())
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ArchiveStop, OSError, ValueError, sqlite3.Error) as exc:
        print(json.dumps({'status': 'stopped', 'reason': str(exc)}, ensure_ascii=False, indent=2))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
