"""Offline format benchmark on actual tick archives; makes no API calls.

Example:
  venv/bin/python scripts/benchmark_tick_formats.py \
    .cache/shioaji_size/2026-09-23.json \
    .cache/shioaji_size/2026-09-23-additional.json
"""

import argparse
import gzip
import json
import pickle
import platform
import random
import statistics
import tempfile
import time
from pathlib import Path

import pandas as pd


FORMATS = ('json', 'json.gz', 'dict.pkl', 'dict.pkl.gz', 'dataframe.pkl', 'dataframe.pkl.gz')


def calculate(frame):
    """One-minute OHLCV, within-minute VWAP and 20-bar simple moving average."""
    work = frame[['ts', 'close', 'volume']].copy()
    work['minute_ns'] = (work['ts'] // 60_000_000_000) * 60_000_000_000
    work['price_volume'] = work['close'] * work['volume']
    bars = work.groupby('minute_ns', sort=True).agg(
        open=('close', 'first'), high=('close', 'max'), low=('close', 'min'),
        close=('close', 'last'), volume=('volume', 'sum'),
        price_volume=('price_volume', 'sum'),
    )
    bars['vwap'] = bars['price_volume'] / bars['volume'].replace(0, float('nan'))
    bars['sma20'] = bars['close'].rolling(20).mean()
    return bars


def encode(payload, frame, fmt):
    if fmt.startswith('json'):
        raw = json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode()
    elif fmt.startswith('dict'):
        raw = pickle.dumps(payload, protocol=5)
    else:
        raw = pickle.dumps({'metadata': {k: v for k, v in payload.items() if k != 'data'},
                            'data': frame}, protocol=5)
    return gzip.compress(raw, compresslevel=9, mtime=0) if fmt.endswith('.gz') else raw


def decode(raw, fmt):
    if fmt.endswith('.gz'):
        raw = gzip.decompress(raw)
    payload = json.loads(raw) if fmt.startswith('json') else pickle.loads(raw)
    return payload['data'] if fmt.startswith('dataframe') else pd.DataFrame(payload['data'])


def stats(values):
    ordered = sorted(values)
    return {'median_ms': round(statistics.median(values), 4),
            'p10_ms': round(ordered[int((len(ordered) - 1) * 0.1)], 4),
            'p90_ms': round(ordered[int((len(ordered) - 1) * 0.9)], 4),
            'repeats': len(values)}


def elapsed(function):
    started = time.perf_counter_ns()
    result = function()
    return (time.perf_counter_ns() - started) / 1_000_000, result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('receipts', type=Path, nargs='+')
    parser.add_argument('--output', type=Path, default=Path('.cache/shioaji_size/2026-09-23-speed-comparison.json'))
    parser.add_argument('--repeats', type=int, default=31)
    args = parser.parse_args()
    if args.repeats < 5:
        parser.error('use at least five repeats')

    payloads, frames, securities, seen = [], [], [], set()
    for receipt in args.receipts:
        record = json.loads(receipt.read_text())
        if record['status'] != 'passed':
            raise ValueError(f'API sample was not completed: {receipt}')
        for entry in record['measurements']:
            identity = (record['date'], entry['exchange'], entry['code'])
            if identity in seen:
                raise ValueError('duplicate samples would overstate the dataset')
            seen.add(identity)
            with gzip.open(entry['path'], 'rt') as handle:
                payload = json.load(handle)
            frame = pd.DataFrame(payload['data'])
            assert str(frame['ts'].dtype) == 'int64'
            payloads.append(payload)
            frames.append(frame)
            securities.append({'date': record['date'], 'code': entry['code'],
                               'name': entry['name'], 'rows': len(frame)})

    reference_bars = [calculate(frame) for frame in frames]
    rng = random.Random(20260924)
    measurements = {fmt: {metric: [] for metric in ('load_to_dataframe', 'compute_loaded', 'load_and_compute', 'encode_and_write')}
                    for fmt in FORMATS}
    sizes, per_stock_sizes = {}, {}
    with tempfile.TemporaryDirectory(prefix='tick_format_speed_') as temporary:
        directory = Path(temporary)
        paths, loaded = {}, {}
        for fmt in FORMATS:
            paths[fmt] = []
            for i, (payload, frame) in enumerate(zip(payloads, frames)):
                path = directory / f'{i}.{fmt}'
                path.write_bytes(encode(payload, frame, fmt))
                restored = decode(path.read_bytes(), fmt)
                pd.testing.assert_frame_equal(restored, frame, check_exact=True)
                pd.testing.assert_frame_equal(calculate(restored), reference_bars[i], check_exact=True)
                paths[fmt].append(path)
            sizes[fmt] = sum(path.stat().st_size for path in paths[fmt])
            per_stock_sizes[fmt] = [path.stat().st_size for path in paths[fmt]]
            loaded[fmt] = [decode(path.read_bytes(), fmt) for path in paths[fmt]]

        def load(fmt):
            return [decode(path.read_bytes(), fmt) for path in paths[fmt]]

        def write(fmt):
            for path, payload, frame in zip(paths[fmt], payloads, frames):
                path.write_bytes(encode(payload, frame, fmt))

        # Warm each format equally. Measurements intentionally include the OS
        # page cache: this is not a cold-disk or external-USB throughput test.
        for _ in range(2):
            for fmt in FORMATS:
                [calculate(frame) for frame in load(fmt)]

        for repeat in range(args.repeats):
            formats = list(FORMATS)
            rng.shuffle(formats)
            for fmt in formats:
                ms, _ = elapsed(lambda: load(fmt))
                measurements[fmt]['load_to_dataframe'].append(ms)
                ms, _ = elapsed(lambda: [calculate(frame) for frame in loaded[fmt]])
                measurements[fmt]['compute_loaded'].append(ms)
                ms, _ = elapsed(lambda: [calculate(frame) for frame in load(fmt)])
                measurements[fmt]['load_and_compute'].append(ms)
                if repeat < 7:
                    ms, _ = elapsed(lambda: write(fmt))
                    measurements[fmt]['encode_and_write'].append(ms)

    report = {
        'python': platform.python_version(), 'pandas': pd.__version__,
        'platform': platform.platform(), 'pickle_protocol': 5, 'gzip_level': 9,
        'securities': securities, 'total_rows': sum(len(frame) for frame in frames),
        'dataframe_memory_bytes': sum(int(frame.memory_usage(index=True, deep=True).sum()) for frame in frames),
        'calculation': 'per-stock one-minute OHLCV, VWAP and rolling 20-bar SMA; no empty-minute padding',
        'measurement_scope': 'entire sample batch per timing, separate per-stock files, same values and dtypes',
        'method': f'{args.repeats} randomized-order rounds after two warmups; medians and p10/p90. Seven encode/write rounds.',
        'limitations': ['Warm OS page cache on local temporary storage, not external-drive speed or cold reads.',
                       'Write timings include serialization and buffered writes, not fsync.',
                       'Real sampled rows only, no duplicated/synthetic scaling.',
                       'Purposefully added stocks improve benchmark size but do not make a representative market-size sample.'],
        'validated': 'Every format preserves exact DataFrame values/dtypes and identical calculated bars.',
        'formats': {fmt: {'bytes': sizes[fmt], 'per_stock_bytes': per_stock_sizes[fmt],
                          **{metric: stats(values) for metric, values in measurements[fmt].items()}}
                    for fmt in FORMATS},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    compact = {'rows': report['total_rows'], 'stocks': len(frames), 'securities': securities,
               'formats': {fmt: {'kib': round(sizes[fmt]/1024, 2),
                                **{metric + '_median_ms': stats(values)['median_ms'] for metric, values in measurements[fmt].items()}}
                           for fmt in FORMATS}, 'report': str(args.output)}
    print(json.dumps(compact, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
