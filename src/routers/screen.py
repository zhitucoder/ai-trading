from fastapi import APIRouter, HTTPException
from src.schemas.screen import (
    TechnicalScreenParams,
    FundamentalScreenParams,
    CombinedScreenParams,
)
from src.services import screen_service

router = APIRouter(prefix='/api/screen', tags=['选股'])


@router.post('/technical')
def technical_screen(params: TechnicalScreenParams):
    try:
        results = screen_service.screen_technical(
            ma_periods=params.ma_periods,
            bullish=params.bullish,
        )
        return {'code': 0, 'data': results, 'total': len(results)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post('/fundamental')
def fundamental_screen(params: FundamentalScreenParams):
    try:
        results = screen_service.screen_fundamental(
            revenue_growth_min=params.revenue_growth_min,
            net_profit_growth_min=params.net_profit_growth_min,
            debt_asset_ratio_max=params.debt_asset_ratio_max,
        )
        return {'code': 0, 'data': results, 'total': len(results)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post('/combined')
def combined_screen(params: CombinedScreenParams):
    try:
        results = screen_service.screen_combined(
            ma_periods=params.ma_periods,
            revenue_growth_min=params.revenue_growth_min,
            net_profit_growth_min=params.net_profit_growth_min,
            debt_asset_ratio_max=params.debt_asset_ratio_max,
        )
        return {'code': 0, 'data': results, 'total': len(results)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
