"""MongoDB Client - 從 MongoDB 取得市場參數

負責:
1. 連接到 MongoDB Atlas
2. 取得期貨月份 (含到期日邏輯)
3. 取得收盤指數
"""

import os
import logging
from datetime import datetime
from typing import Optional, Dict, Any

import pytz
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, OperationFailure

logger = logging.getLogger(__name__)

# 台灣時區
TW_TIMEZONE = pytz.timezone('Asia/Taipei')


class MongoDBClient:
    """MongoDB 客戶端

    負責從 MongoDB 取得市場參數:
    - 期貨月份 (futures_month)
    - 契約到期日 (expiration_date)
    - 收盤指數 (closing_index)
    """

    def __init__(self):
        """初始化 MongoDB 客戶端"""
        self._uri = os.getenv('MONGO_URI')
        self._db_name = os.getenv('MONGO_DB', 'market_data')
        self._collection_name = os.getenv('MONGO_COLLECTION', 'taifex_option_daily')

        self._client: Optional[MongoClient] = None
        self._db = None
        self._collection = None

        # 快取資料
        self._futures_month: Optional[str] = None
        self._expiration_date: Optional[str] = None
        self._closing_index: Optional[float] = None

    def connect(self) -> bool:
        """連接到 MongoDB

        Returns:
            是否連接成功
        """
        if not self._uri:
            logger.error("缺少 MONGO_URI 環境變數")
            return False

        try:
            self._client = MongoClient(self._uri)
            # 測試連接
            self._client.admin.command('ping')

            self._db = self._client[self._db_name]
            self._collection = self._db[self._collection_name]

            logger.info(f"已連接到 MongoDB: {self._db_name}.{self._collection_name}")
            return True

        except ConnectionFailure as e:
            logger.error(f"無法連接到 MongoDB: {e}")
            return False
        except Exception as e:
            logger.error(f"MongoDB 連接錯誤: {e}")
            return False

    def disconnect(self) -> None:
        """斷開 MongoDB 連接"""
        if self._client:
            self._client.close()
            self._client = None
            self._db = None
            self._collection = None
            logger.info("已斷開 MongoDB 連接")

    def fetch_market_parameters(self) -> bool:
        """從 MongoDB 取得所有市場參數

        取得:
        - session: "future_month" 的 期貨月份 和 契約到期日
        - session: "twse_taiex" 的 收盤指數

        Returns:
            是否成功取得資料
        """
        if not self._collection:
            if not self.connect():
                return False

        try:
            # 取得期貨月份資料
            future_month_doc = self._collection.find_one({"session": "future_month"})
            if future_month_doc:
                self._futures_month = future_month_doc.get("期貨月份")
                self._expiration_date = future_month_doc.get("契約到期日")
                logger.info(f"期貨月份: {self._futures_month}, 契約到期日: {self._expiration_date}")
            else:
                logger.warning("找不到 session: future_month 的文件")
                return False

            # 取得收盤指數
            twse_doc = self._collection.find_one({"session": "twse_taiex"})
            if twse_doc:
                self._closing_index = twse_doc.get("收盤指數")
                logger.info(f"收盤指數: {self._closing_index}")
            else:
                logger.warning("找不到 session: twse_taiex 的文件")
                return False

            return True

        except OperationFailure as e:
            logger.error(f"MongoDB 查詢錯誤: {e}")
            return False
        except Exception as e:
            logger.error(f"取得市場參數時發生錯誤: {e}")
            return False

    def get_futures_month(self) -> Optional[str]:
        """取得期貨月份 (含到期日邏輯)

        邏輯:
        - 如果今天是契約到期日 AND 台灣時間 >= 14:00
        - 則返回下個月份 (MM+1, 12月變01月且年份+1)
        - 否則返回當前期貨月份

        Returns:
            期貨月份 (格式: YYYYMM, 如 202603)
        """
        if not self._futures_month:
            if not self.fetch_market_parameters():
                return None

        # 檢查是否需要切換到下個月份
        if self._should_use_next_month():
            return self._calculate_next_month(self._futures_month)

        return self._futures_month

    def get_closing_index(self) -> Optional[float]:
        """取得收盤指數

        Returns:
            收盤指數 (如 34056.0)
        """
        if self._closing_index is None:
            if not self.fetch_market_parameters():
                return None

        return self._closing_index

    def get_expiration_date(self) -> Optional[str]:
        """取得契約到期日

        Returns:
            契約到期日
        """
        if not self._expiration_date:
            if not self.fetch_market_parameters():
                return None

        return self._expiration_date

    def _should_use_next_month(self) -> bool:
        """判斷是否應該使用下個月份

        條件:
        - 今天已經超過契約到期日，或
        - 今天是契約到期日 AND 台灣時間 >= 14:00

        Returns:
            是否應該使用下個月份
        """
        if not self._expiration_date:
            return False

        try:
            # 取得台灣時間
            now_tw = datetime.now(TW_TIMEZONE)
            today_str = now_tw.strftime("%Y%m%d")

            # 標準化到期日格式 (移除可能的分隔符號)
            exp_date_str = str(self._expiration_date).replace("-", "").replace("/", "")

            # 比較日期
            today_int = int(today_str)
            exp_date_int = int(exp_date_str)

            # 如果今天已經超過到期日，一定要用下個月
            if today_int > exp_date_int:
                logger.info(f"今天 ({today_str}) 已超過到期日 ({exp_date_str})，切換到下個月份")
                return True

            # 如果今天是到期日且已過 14:00，也要用下個月
            if today_int == exp_date_int and now_tw.hour >= 14:
                logger.info(f"今天是到期日 ({exp_date_str}) 且已過 14:00，切換到下個月份")
                return True

            return False

        except Exception as e:
            logger.error(f"判斷到期日邏輯時發生錯誤: {e}")
            return False

    def _calculate_next_month(self, current_month) -> str:
        """計算下個月份

        Args:
            current_month: 當前月份 (格式: YYYYMM，可為字串或整數)

        Returns:
            下個月份 (格式: YYYYMM)
            例如: 202603 -> 202604, 202612 -> 202701
        """
        try:
            # 確保轉換為字串
            current_month_str = str(current_month)
            year = int(current_month_str[:4])
            month = int(current_month_str[4:6])

            # 計算下個月
            if month == 12:
                year += 1
                month = 1
            else:
                month += 1

            next_month = f"{year}{month:02d}"
            logger.info(f"切換月份: {current_month_str} -> {next_month}")
            return next_month

        except Exception as e:
            logger.error(f"計算下個月份時發生錯誤: {e}")
            return str(current_month)

    def get_all_parameters(self) -> Dict[str, Any]:
        """取得所有市場參數

        Returns:
            包含所有市場參數的字典
        """
        return {
            'futures_month': self.get_futures_month(),
            'closing_index': self.get_closing_index(),
            'expiration_date': self.get_expiration_date()
        }
