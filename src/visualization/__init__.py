"""5 分 K IV 指標視覺化模組

此模組提供 XQ 風格的 IV 指標副圖繪製功能。

主要功能:
    - 黃線顯示 CIV %b
    - 紅綠柱顯示 price_pb - civ_pb
    - 圖上方顯示最新數值

使用範例:
    ```python
    from visualization import IndicatorResult, render_panel_from_rows

    rows = [...]  # List[IndicatorResult]
    fig = render_panel_from_rows(rows)
    fig.show()
    ```

匯出:
    - IndicatorResult: 資料模型
    - rows_to_dataframe: 轉換函數
    - validate_panel_dataframe: 驗證函數
    - build_top_annotations: 標註建構
    - plot_indicator_panel: 繪圖函數
    - render_panel_from_rows: 一站式入口
"""

from .models import IndicatorResult
from .validators import validate_panel_dataframe, check_data_availability
from .annotations import build_top_annotations
from .plotly_chart import (
    rows_to_dataframe,
    plot_indicator_panel,
    render_panel_from_rows,
    COLORS,
    Y_AXIS_RANGE,
)

__all__ = [
    # Models
    'IndicatorResult',

    # Functions
    'rows_to_dataframe',
    'validate_panel_dataframe',
    'check_data_availability',
    'build_top_annotations',
    'plot_indicator_panel',
    'render_panel_from_rows',

    # Constants
    'COLORS',
    'Y_AXIS_RANGE',
]
