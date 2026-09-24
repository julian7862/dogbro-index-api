"""Build a public, credential-free standalone crawler from an explicit allowlist.

Run from the repository root: venv/bin/python scripts/build_tick_crawler_bundle.py
This exports only an unstarted plan; a live archive must be moved privately whole.
"""

import gzip
import hashlib
import json
import shutil
import sqlite3
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.data.tick_archive import Archive, single_worker

KIT = ROOT / 'tick_crawler'
VERSION = '2026.09.24.1'
COPIED = [
    'download_ticks.py',
    'src/data/tick_archive.py',
    'src/data/shioaji_history.py',
    'src/data/equity_universe.py',
    'data/reference/twse_holidays_2026.json',
    'docs/HISTORICAL_TICKS.md',
    'docs/TICK_STORAGE_CAPACITY_PLAN.md',
    'tests/test_tick_archive.py',
    'tests/test_shioaji_history.py',
    'tests/test_download_ticks.py',
    'tests/test_equity_universe.py',
]
STATIC = [
    '.gitignore', '.env.example', 'README.md', 'prepare.py', 'pytest.ini',
    'requirements.txt', 'requirements-dev.txt', 'requirements-analysis.txt',
    'tests/test_prepare.py',
]
GENERATED = [
    'src/__init__.py', 'src/data/__init__.py',
    'seed/manifest.sqlite3.gz', 'seed/universe.json', 'seed/snapshot.json',
]


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot():
    source_path = ROOT / 'data/historical_ticks/manifest.sqlite3'
    if not source_path.is_file():
        raise RuntimeError('the source plan is missing')
    with single_worker(ROOT / '.cache/shioaji-history.lock'):
        source = sqlite3.connect(source_path.as_uri() + '?mode=ro', uri=True)
        try:
            counts = dict(source.execute('SELECT status, COUNT(*) FROM jobs GROUP BY status'))
            if not counts or set(counts) - {'pending', 'listing_history_unverified'}:
                raise RuntimeError('only an unstarted plan may be published')
            if source.execute('SELECT COUNT(*) FROM ledger').fetchone()[0]:
                raise RuntimeError('usage history exists; move the live archive privately')
            with tempfile.TemporaryDirectory(prefix='tick-public-seed-') as temp:
                clean = Archive(Path(temp))
                try:
                    with clean.db:
                        clean.db.executemany(
                            'INSERT INTO jobs(exchange,code,day,status) VALUES (?,?,?,?)',
                            source.execute('SELECT exchange,code,day,status FROM jobs ORDER BY exchange,code,day'))
                        for key in ('plan', 'plan_signature', 'universe_as_of'):
                            row = source.execute('SELECT key,value FROM meta WHERE key=?', (key,)).fetchone()
                            if row is None:
                                raise RuntimeError(f'missing public plan metadata: {key}')
                            clean.db.execute('INSERT INTO meta VALUES (?,?)', row)
                    plan = clean.meta('plan')
                finally:
                    clean.close()
                database = Path(temp) / 'manifest.sqlite3'
                compressed = KIT / 'seed/manifest.sqlite3.gz'
                compressed.parent.mkdir(parents=True, exist_ok=True)
                with database.open('rb') as src, compressed.open('wb') as raw:
                    with gzip.GzipFile(filename='', fileobj=raw, mode='wb', mtime=0) as dst:
                        shutil.copyfileobj(src, dst)
                shutil.copyfile(ROOT / 'data/historical_ticks/universe.json', KIT / 'seed/universe.json')
                metadata = {
                    'created_at': datetime.now(timezone.utc).isoformat(),
                    'plan': plan, 'jobs': counts, 'stored_ticks': 0,
                    'database_sha256': sha256(database),
                    'excluded': ['credentials', 'CA', 'usage_history', 'tick_data'],
                }
                (KIT / 'seed/snapshot.json').write_text(json.dumps(metadata, indent=2) + '\n')
                return metadata
        finally:
            source.close()


def main():
    for relative in COPIED:
        destination = KIT / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, destination)
    for relative in ('src/__init__.py', 'src/data/__init__.py'):
        (KIT / relative).write_text('')
    metadata = snapshot()
    files = sorted(COPIED + STATIC + GENERATED)
    package = {'version': VERSION, 'snapshot': metadata['plan'],
               'sha256': {relative: sha256(KIT / relative) for relative in files}}
    (KIT / 'PACKAGE.json').write_text(json.dumps(package, indent=2) + '\n')
    release = ROOT / '.cache/releases' / f'tick-crawler-{VERSION}.zip'
    release.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(release, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for relative in sorted(files + ['PACKAGE.json']):
            archive.write(KIT / relative, arcname=f'tick_crawler/{relative}')
    print(json.dumps({'release': str(release), 'bytes': release.stat().st_size,
                      'sha256': sha256(release), 'files': len(files) + 1,
                      'jobs': metadata['jobs']}, indent=2))


if __name__ == '__main__':
    main()
