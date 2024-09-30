from fastapi import APIRouter, HTTPException, Depends
from loader import get_goods_cache_service

from services.good.service import GoodsCacheService

router = APIRouter(prefix='/goods', tags=['Goods'])

@router.get("")
def get_goods(cache_service: GoodsCacheService = Depends(get_goods_cache_service)):
    return cache_service.get_goods()