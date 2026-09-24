# 台股歷史逐筆成交下載

容量與頻繁回測的儲存建議見 [Tick 資料容量與回測儲存規劃](TICK_STORAGE_CAPACITY_PLAN.md)：
本區間 Parquet 主檔以 10 GiB 作基準、保守預留 25 GiB；快取與備份等整體預算 100 GiB。

入口是 `download_ticks.py`，不需要啟動 `main.py`、MongoDB 或 Docker。沿用專案
Python 環境與 `.env`，實測 SDK 1.3.2 的模擬登入及 usage 查詢成功，沒有升級套件。
工具只暴露登入、流量、合約和 ticks 查詢，不啟用 CA、不下單。

## 目前準備狀態

2026/09/24 已快取證交所 ISIN 清單，規劃 2026/03/01～2026/09/24：

- 上市（含清單中的創新板）1,085 檔、上櫃 893 檔，合計 1,978 檔普通股。
- 使用 CFI `ES` 分類，排除 ETF、權證及特別股。
- 144 個候選交易日；281,833 個待下載股票日。
- 另外 2,999 個股票日在目前市場掛牌日前，標為 `listing_history_unverified`。
- 已確認每日額度 524,288,000 bytes（500 MiB）。
- **正式資料集尚未開始下載；盤中批次下載已確認會被拒絕。**
- 2026/09/24 11:25 完成一次真實 API 整合測試：2330、2026/03/02，取得
  13,714 筆 tick（09:00:05.410317000～14:30:00），壓縮後 115,152 bytes。
  驗證原始欄位完整存回、重新開啟及 SHA-256 成功，16.45 秒完成並登出。
  測試使用暫存目錄且已刪除 tick 檔，沒有混入正式資料集。

下載器完成並通過離線測試，不代表整份資料集已完成。每日 1,000 次的工具預算，
光現有待下載任務就至少需要 282 個流量週期；實際還可能受每日流量、停牌、缺漏及
磁碟空間影響。這不是券商核准的批次資料方案，低速也不能保證全帳號完全不受限制。

## 外接硬碟

使用者預計將 tick 與進度表放在外接硬碟。接上硬碟後，把下列 `YOUR_DISK` 換成
實際名稱；路徑有空格時保留引號。**不要直接使用範例名稱。**

先把已建立的清單及進度表複製過去（目前只有 metadata，沒有 tick）：

```bash
cp -R data/historical_ticks "/Volumes/YOUR_DISK/shioaji_ticks"
venv/bin/python download_ticks.py --output "/Volumes/YOUR_DISK/shioaji_ticks" status
```

`cp` 範例的目的地必須尚不存在，避免產生多一層目錄。日後換硬碟或電腦時，
請在 worker 停止後複製**整個**資料夾，包含 `manifest.sqlite3`、`universe.json` 和
`ticks/`。進度表保存相對路徑，搬移後可直接續跑。不要只複製 tick 檔案。

工具會在初始化、查詢前與寫檔前確認 `/Volumes/<名稱>` 仍為掛載點。
外接硬碟未掛載時停止，不會自動建立同名假掛載資料夾。預設保留 5 GiB 可用空間。
`run` 必須明確提供 `--output`，避免忘記路徑時將 tick 寫進本機的預設 metadata 目錄。
請使用支援足夠檔案數量及單一檔案大小的檔案系統，並保持電腦喚醒、硬碟連接。

## 執行

所有全域參數（例如 `--output`）放在子命令**前面**。在台灣時間 16:00 之後：

```bash
# 先驗證一個股票日，檔案會成為正式快取的一部分
venv/bin/python download_ticks.py --output "/Volumes/YOUR_DISK/shioaji_ticks" run --max-requests 1

# 檢查下載進度及檔案 checksum
venv/bin/python download_ticks.py --output "/Volumes/YOUR_DISK/shioaji_ticks" status
venv/bin/python download_ticks.py --output "/Volumes/YOUR_DISK/shioaji_ticks" verify

# 接續一個有上限的批次
venv/bin/python download_ticks.py --output "/Volumes/YOUR_DISK/shioaji_ticks" run
```

每個交易日盤後執行同一命令即可續跑；**目前未安裝任何排程或背景服務**。
當日查詢預算耗盡後，不要靠重啟、新 output 或換帳號繞過預算。
週末、休市日不假設流量重置；重置週期使用交易日上午 08:00。
目前參考日曆只支援 2026，跨年之前需更新日曆與年度支援，不能直接跑到 2027。
此設計刻意在資料來源不明確時停止，不會無人監督地自動跳過錯誤。

從空資料夾建立計畫（會抓取公開股票清單，但不登入 Shioaji）：

```bash
venv/bin/python download_ticks.py --output "/Volumes/YOUR_DISK/shioaji_ticks" plan \
  --start 2026-03-01 --end 2026-09-24
```

小範圍研究可用另一個獨立資料夾搭配 `plan --codes 2330,2317` 或 `--market TSE`。
計畫建立後日期及股票集合固定，避免縮小參數卻意外繼續舊任務。不要讓多份計畫
同時下載同一股票日。CLI 以專案共用鎖阻止自身重複啟動，但不能控制其他程式或電腦。

## 限速、流量與失敗處理

依 [Shioaji 合理使用規範](https://sinotrade.github.io/zh/tutor/limit/) 設計：

| 項目 | 工具行為 |
| --- | --- |
| 執行時段 | 每日台灣時間 16:00～次日 08:00，其他時間登入前退出；等待、合約載入及流量查詢後再次檢查 |
| 連線 | 一次 run 一個模擬登入，結束 logout；不自動重連 |
| 查詢 | 單 worker，一個股票日一次 AllDay ticks；至少間隔 5 秒，重啟仍保留間隔紀錄 |
| 次數預算 | 每個流量週期最多 1,000 次，存在 SQLite；`--max-requests` 可縮小本次批量 |
| 本工具流量 | 預設每週期最多約 200 MiB 的已觀測 tick 增量，可用 `--daily-mib` 調低 |
| 全帳號用量 | 查詢前後讀取 usage，使用量達 50% 前預留至少 100 MiB；也參考最大已觀測單次回應的兩倍 |
| 不明回應 | 空值先查 usage，再記錄缺漏並停止；不當作零成交，不立即重試 |
| 錯誤 | 登入、SDK、寫檔等錯誤停止；持久化 halt，後續 run 不再登入／查詢直到明確處理 |
| 中断 | 先記錄 in_flight；已完整寫好的檔案可恢復，未完成回應需人工確認 |
| 不明用量 | 回應已儲存但後續 usage 未完成時阻止續跑；人工解除後耗盡舊週期的本工具預算，避免重啟漏算 |

API 無法事先告知一整天 tick 的回應大小；保留額度是保守緩衝，**不是絕不超額的數學保證**。
真實測試也觀察到 tick 前後 usage 計數沒有立即改變，差值 0 不能解讀成零流量；
本工具的逐次增量預算可能受計數延遲影響，仍需搭配全帳號額度、保留量及次數上限。
其他程式也可能消耗同帳號配額。既有 `main.py` 的服務有每 5 秒 snapshot 輪詢，
這和新下載器是不同流程，仍需依官方規範另行修正或避免同時執行。
合約初次載入也可能消耗流量，會在 tick 前重新確認全帳號額度。

退出碼：0 完成本次批量；2 保護性停止（時段、預算、待診斷問題等）；1 其他錯誤。
看到 2 不應立即無限重啟。`status` 不會登入或消耗流量；`usage` 會登入一次。

遇到 halt，先調查流量、官方交易日、個股停牌、上市／轉板日期及券商狀態。確定
原因後，可保留缺漏並繼續其他工作：

```bash
venv/bin/python download_ticks.py --output "/Volumes/YOUR_DISK/shioaji_ticks" clear-halt \
  --reason "寫下已確認的原因；該股票日保留為缺漏"
```

如果已排除問題且確實要重新查詢，加 `--retry-failed`。這是顯式人工動作，並不會
重設流量／次數帳本，也不會把已完成的 tick 檔案排入重抓。

## 儲存格式與讀取

```text
shioaji_ticks/
  universe.json
  manifest.sqlite3
  ticks/2026-03-02/TSE/2330.json.gz
  ticks/2026-03-02/OTC/6488.json.gz
```

檔案以 gzip 壓縮，內有來源、股票代碼、交易所、日期、SDK 版本與原始欄位陣列。
保留 `ts, close, volume, bid_price, bid_volume, ask_price, ask_volume, tick_type`，
也保留 SDK 額外傳回的等長欄位。不做聚合、不去除同一時間戳的多筆成交。
先寫暫存檔、fsync 後原子取代，再更新進度表及 SHA-256。

```python
import gzip
import json
import pandas as pd

with gzip.open('/Volumes/YOUR_DISK/shioaji_ticks/ticks/2026-03-02/TSE/2330.json.gz', 'rt') as f:
    archive = json.load(f)
df = pd.DataFrame(archive['data'])
df['datetime'] = pd.to_datetime(df['ts'])  # 已是台灣市場牆鐘時間，不要再加八小時
```

`ts` 是完整整數奈秒值。若用 JavaScript 讀取，勿以一般 Number 處理奈秒時間戳，
需使用保留大整數的 JSON parser。

## 資料完整性邊界

官方[歷史行情說明](https://sinotrade.github.io/zh/tutor/market_data/historical/)提供股票 ticks，
但要求使用仍可解析的商品合約。工具下載的是該 API 回傳的整日逐筆資料；不能把它
宣稱為包含所有交易管道／零股／下市商品的交易所原始完整資料庫。

ISIN 是**現在的清單**，不是每天的歷史成分：

- 已下市、已撤銷或更名／換代碼商品可能缺席；清單不存在的歷史商品無法自動計數。
- 清單中的「上市日」可能是由上櫃轉上市的日期，之前的資料不會自動算作沒有成交。
  這些股票日列為 `listing_history_unverified`，不消耗歷史查詢額度。
- 缺合約、空回應或停牌都不會自動標記 done。進度中保留具體缺漏狀態。
- 完整的 point-in-time 研究必須另備歷史上市／下市／轉板清單，並确认 Shioaji 合約可查。

可在建立計畫前使用 `plan --universe /path/to/verified_universe.json`。格式是：

```json
{
  "as_of": "2026-09-24",
  "stocks": [
    {"exchange": "TSE", "code": "2330", "listed_on": "1994-09-05"}
  ]
}
```

`listed_on` 需由你驗證；同一份計畫更正它後再 plan，會將符合日期的未核對股票日
轉為 pending。這個簡單 schema 無法表示分段轉板歷史；轉板與已下市資料仍須分別
核對供應商覆蓋能力，不能只改日期便宣稱補齊。

交易日快取在 `data/reference/twse_holidays_2026.json`，列出年度行事曆及已確認的臨時
休市來源。新增颱風休市或延長區間前需更新；休市日不等於全部個股均有交易。

## 測試

### 儲存格式與計算速度實測（2026/09/24）

對 2026/09/23 的真實資料新增查詢 2317、3481、6488，合併原始五檔，共
8 檔、57,162 筆 tick。所有原始樣本仍在暫存目錄，不是正式外接硬碟資料集。
這三檔是指定樣本，可擴大效能測試，但不能用來提高全市場平均值估計的統計可信度。
先前五檔外推的約 9 MiB／全市場一天不適合拿來規劃容量，尚未取得可靠替代估計。

以相同欄位、數值與 dtype 比較六種格式；每檔各存一個檔案。先暖機兩次，再以
隨機格式順序量測 31 輪，以下是**整批八檔**的中位數。gzip level=9，pickle protocol=5，
Python 3.13.3、pandas 3.0.1。計算包含各股 1 分 OHLCV、VWAP、20 根移動平均；
每種格式讀回的 DataFrame 及計算結果均已逐值驗證相同。

| 格式 | 大小 KiB | 讀取並還原 DataFrame ms | 已載入資料計算 ms | 讀取＋計算 ms |
| --- | ---: | ---: | ---: | ---: |
| JSON | 2703.4 | 55.22 | 16.92 | 72.22 |
| JSON.gz | 477.1 | 56.94 | 16.97 | 74.16 |
| 字典 pkl | 2574.2 | 39.34 | 16.85 | 56.34 |
| 字典 pkl.gz | 479.7 | 41.08 | 16.94 | 57.85 |
| DataFrame pkl | 3582.6 | 1.11 | 16.53 | 17.59 |
| DataFrame pkl.gz | 493.7 | 2.78 | 16.48 | 19.27 |

直接儲存 DataFrame 省去從 Python list 建立數值陣列的成本。這批資料的 DataFrame
pkl.gz 比 JSON.gz 大約 3.5%，讀入快約 20 倍、讀入加計算快約 3.8 倍；
資料已載入後，計算時間接近。這些倍數只適用本次樣本與測量條件。

測試使用**本機 OS page cache**，不是外接硬碟或冷讀測試。寫入測試只量序列化與
buffered write、不包含 fsync，gzip 的壓縮成本也不能忽略：整批 JSON.gz 寫入約
489 ms，DataFrame pkl.gz 約 720 ms（各七輪中位數）。下載器目前仍使用 JSON.gz，
本次只有基準測試，沒有變更正式儲存格式。

可直接使用已保存樣本重跑，不會呼叫 API：

```bash
venv/bin/python scripts/benchmark_tick_formats.py \
  .cache/shioaji_size/2026-09-23.json \
  .cache/shioaji_size/2026-09-23-additional.json
```

詳細結果（含 p10/p90）在 `.cache/shioaji_size/2026-09-23-speed-comparison.json`。
樣本位於暫存目錄，若被系統清除，需先還原樣本；腳本不會自動重新查詢 API。

### 離線及 API 整合測試

```bash
venv/bin/python -m pytest tests/test_tick_archive.py tests/test_shioaji_history.py \
  tests/test_equity_universe.py tests/test_download_ticks.py -q -o addopts=''
```

上面 65 項測試使用假 API，不消耗真實流量；包括跨盤中界線、預算、重啟、空回應、
錯誤、原始時間戳與檔案損壞。

另外有一次真實 API 整合測試（預設跳過，必須明確 opt in）：

```bash
RUN_SHIOAJI_LIVE_TEST=1 venv/bin/python -m pytest tests/test_shioaji_live.py -s -q -o addopts=''
```

只登入一次、解析 2330、查一次 2026/03/02 AllDay ticks、驗證暫存檔並登出，不啟動
批次排程。結果留在 `.cache/shioaji_live/YYYY-MM-DD.json`；同一天已有紀錄即跳過，
避免重複消耗盤中查詢次數。這是明確要求的少量連線測試，沒有放寬下載器的盤後限制。
目前真實 API 查詢與暫存檔完整往返已驗證；外接硬碟寫入、完整批次流程仍待盤後及
硬碟接上再驗證。
