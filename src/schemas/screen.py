from pydantic import BaseModel
from typing import Optional


class TechnicalScreenParams(BaseModel):
    ma_periods: list[int] = [5, 10, 20, 60]
    bullish: bool = True


class FundamentalScreenParams(BaseModel):
    revenue_growth_min: Optional[float] = 20.0
    net_profit_growth_min: Optional[float] = 20.0
    debt_asset_ratio_max: Optional[float] = 50.0


class CombinedScreenParams(BaseModel):
    ma_periods: list[int] = [5, 10, 20, 60]
    revenue_growth_min: float = 20.0
    net_profit_growth_min: float = 20.0
    debt_asset_ratio_max: float = 50.0
