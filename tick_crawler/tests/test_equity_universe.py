import pytest

from src.data.equity_universe import parse_isin


def html(rows):
    return ('<table>' + ''.join('<tr>' + ''.join(f'<td>{c}</td>' for c in row) + '</tr>' for row in rows) + '</table>').encode('cp950')


def test_ordinary_shares_include_innovation_board_but_not_etfs_and_warrants():
    source = html([
        ['2330　台積電', 'TW0002330008', '1994/09/05', '上市', '半導體', 'ESVUFR', ''],
        ['2258　鴻華先進-創', 'TW0002258001', '2023/11/20', '上市', '汽車', 'ESVUFR', ''],
        ['0050　元大台灣50', 'ETF', '2003/06/30', '上市', '', 'CEOGEU', ''],
        ['123456　認購權證', 'WARRANT', '2026/03/02', '上市', '', 'RWSXXR', ''],
    ])
    stocks = parse_isin(source, 'TSE')
    assert [s['code'] for s in stocks] == ['2330', '2258']
    assert stocks[0]['listed_on'] == '1994-09-05'
    assert stocks[1]['name'] == '鴻華先進-創'


def test_missing_or_changed_schema_cannot_become_successful_empty_universe():
    with pytest.raises(ValueError, match='no ordinary shares'):
        parse_isin(b'<html>Service unavailable</html>', 'OTC')


def test_duplicate_codes_are_not_silently_accepted():
    row = ['6488　環球晶', 'TW0006488000', '2015/09/25', '上櫃', '半導體', 'ESVUFR', '']
    with pytest.raises(ValueError, match='duplicate'):
        parse_isin(html([row, row]), 'OTC')
