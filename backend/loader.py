from RestAPI.RemonlineAPI import RemonlineAPI
from config import REMONLINE_API_KEY_PROD, CATEGORIES_IGNORE_IDS
from services.good.service import GoodsCacheService

CRM = RemonlineAPI(REMONLINE_API_KEY_PROD)
warehouse = CRM.get_main_warehouse_id()
branch = CRM.get_branches()["data"][0]["id"]
goods_cache_service = GoodsCacheService(CRM, warehouse, CATEGORIES_IGNORE_IDS)


def get_goods_cache_service():
    return goods_cache_service



