from fastapi import APIRouter
from ..strategies.profile import generate_profile

router = APIRouter()


@router.get('/profile/{stock_code}')
def get_profile(stock_code: str):
    return generate_profile(stock_code)
