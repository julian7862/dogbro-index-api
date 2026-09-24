# 台股 Tick 下載搬機套件

這個資料夾可單獨使用，不依賴外層專案、不需要 Docker、MongoDB 或 CA 憑證。
歷史行情只用 API Key／Secret；程式固定模擬登入，不下單。

## 內含

- 下載程式及所有必要 Python 模組。
- 2026 年交易日參考日曆與 1,978 檔上市／上櫃普通股清單。
- 2026/03/01～09/24 的壓縮進度快照：281,833 個待下載股票日、2,999 個待核對上市／轉板歷史股票日。
- 安裝版本、離線測試、容量與回測儲存說明。
- 檔案 SHA-256 檢查清單 `PACKAGE.json`。

這是尚未開始正式下載的計畫快照，**不含實際 tick、私人 API Key／Secret、CA 或憑證密碼**。
GitHub 專案為公開專案；只有 `.env.example` 可以下載。請在新電腦本機填入金鑰，
或自行用私人方式搬移原電腦這個資料夾裡的 `.env`，不要上傳到 GitHub。

## 1. 安裝

新電腦同樣使用 **Mac + Python 3.13 + venv**。目前 live API 驗證使用 Python 3.13.3、Shioaji 1.3.2。
下載 ZIP 後進入其中的 `tick_crawler`；也可以直接將本資料夾複製到新電腦。
請新建虛擬環境，不要搬移舊電腦的 `venv`。

macOS：

```bash
cd tick_crawler
python3.13 -m venv venv
source venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

用編輯器在 `.env` 填入 `SJ_KEY`、`SJ_SEC`。不要把已填好金鑰的 `.env` 用範本覆蓋。
CA 不用搬來。以下指令都在已啟用的 `venv` 中執行；開新終端機時先進入資料夾，
再執行 `source venv/bin/activate`。

## 2. 還原進度到外接硬碟

先接上硬碟，目的資料夾必須尚不存在。把以下範例路徑換成實際位置：

macOS：

```bash
python prepare.py --verify-only
python prepare.py --output "/Volumes/YOUR_DISK/shioaji_ticks"
python download_ticks.py --output "/Volumes/YOUR_DISK/shioaji_ticks" status
```

`prepare.py` 會驗證雜湊、解壓 SQLite、核對任務數目；不呼叫任何外部 API。
它拒絕覆蓋已存在的目的資料夾。已有實際進度時應搬移完整 archive 資料夾，不能
用這份初始快照蓋掉新進度，也不應在兩台電腦同時下載同一份計畫。

## 3. 測試登入，盤後下載

```bash
# 只登入一次、查流量後登出，不抓 tick
python download_ticks.py --output "/Volumes/YOUR_DISK/shioaji_ticks" usage

# 台灣時間16:00後，先下載一個股票日
python download_ticks.py --output "/Volumes/YOUR_DISK/shioaji_ticks" run --max-requests 1
python download_ticks.py --output "/Volumes/YOUR_DISK/shioaji_ticks" verify

# 繼續一個有上限的批次
python download_ticks.py --output "/Volumes/YOUR_DISK/shioaji_ticks" run
```

全域參數 `--output` 必須放在 `run/status/usage` 等子命令前。
只有 16:00～隔日08:00（Asia/Taipei）允許批次下載；至少間隔5秒、每個流量週期最多
1,000次；全帳號額度、流量預算、空間不足及錯誤會停止，不自動重試。
進度保存在外接硬碟，重啟後沿用。沒有安裝排程或背景服務。

退出碼0表示本次批量完成；2表示保護性停止；1表示其他錯誤。
遇到錯誤請先看 `status`，依說明診斷後才用 `clear-halt --reason "已確認的原因"`。
空資料不會自動視為零成交或下載完成。

## 空間、格式與範圍限制

目前程式寫入 **JSON.gz**；Parquet／pkl 是下一階段儲存規劃，尚未改變下載格式。
參考預算為主檔10～25 GiB、連同快取與備份整體100 GiB；詳見 [容量規劃](docs/TICK_STORAGE_CAPACITY_PLAN.md)。
完整限制與錯誤處理見 [下載說明](docs/HISTORICAL_TICKS.md)，該文件沿用原專案命令，
本套件應以本頁 `venv` 路徑與 `prepare.py` 還原流程為準。

目前使用當前普通股清單，不能宣稱已涵蓋全部歷史下市／轉板商品。參考日曆只支援
2026 年；跨年前需更新日曆及年度支援。初始待下載量至少需要282個1,000次預算週期，
不是一晚或一週就能完整抓完的工具。

## 離線檢查

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

套件只包含離線測試，不會因為執行測試而使用券商金鑰。
下載只需要 `requirements.txt`；回測分析才另外安裝 `requirements-analysis.txt`。
