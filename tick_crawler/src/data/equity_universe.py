"""Cache the exchanges' current ISIN list, including explicit listing dates."""

import json
import re
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

SOURCES = {
    'TSE': 'https://isin.twse.com.tw/isin/C_public.jsp?strMode=2',
    'OTC': 'https://isin.twse.com.tw/isin/C_public.jsp?strMode=4',
}


class IsinTable(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows, self.row, self.cell = [], [], None

    def handle_starttag(self, tag, attrs):
        if tag == 'tr':
            self.row = []
        elif tag in ('td', 'th'):
            self.cell = []

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag in ('td', 'th') and self.cell is not None:
            self.row.append(''.join(self.cell).strip())
            self.cell = None
        elif tag == 'tr' and self.row:
            self.rows.append(self.row)


def parse_isin(raw: bytes, exchange: str):
    parser = IsinTable()
    parser.feed(raw.decode('cp950'))
    stocks = []
    for row in parser.rows:
        # ES = common/ordinary shares; exclude ETFs, warrants, preferred shares.
        if len(row) < 6 or not row[5].startswith('ES'):
            continue
        parts = row[0].split(maxsplit=1)
        if len(parts) != 2 or not re.fullmatch(r'[A-Za-z0-9]+', parts[0]):
            raise ValueError('unrecognized ISIN code/name cell')
        listed = datetime.strptime(row[2], '%Y/%m/%d').date().isoformat()
        stocks.append({'exchange': exchange, 'code': parts[0], 'name': parts[1],
                       'isin': row[1], 'listed_on': listed, 'cfi': row[5]})
    if not stocks:
        raise ValueError(f'no ordinary shares found for {exchange}; inspect ISIN format')
    if len({s['code'] for s in stocks}) != len(stocks):
        raise ValueError('duplicate stock codes in exchange list')
    return stocks


def load_universe(path: Path, refresh=False):
    if path.exists() and not refresh:
        return json.loads(path.read_text())
    stocks = []
    for exchange, url in SOURCES.items():
        request = Request(url, headers={'User-Agent': 'dogbro-historical-archive/1.0'})
        with urlopen(request, timeout=45) as response:
            raw = response.read(10 * 1024 * 1024 + 1)
        if len(raw) > 10 * 1024 * 1024:
            raise ValueError('unexpectedly large exchange response')
        stocks.extend(parse_isin(raw, exchange))
    unique = {}
    for stock in stocks:
        key = (stock['exchange'], stock['code'])
        if key in unique and stock['isin'] != unique[key]['isin']:
            raise ValueError('conflicting security identifiers')
        unique[key] = stock
    payload = {'as_of': datetime.now(ZoneInfo('Asia/Taipei')).isoformat(),
               'scope': 'current TSE/OTC ordinary shares (CFI starts ES); excludes delisted securities',
               'sources': SOURCES, 'stocks': list(unique.values())}
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.partial')
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    temporary.replace(path)
    return payload
