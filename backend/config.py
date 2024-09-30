import os
from dotenv import load_dotenv

load_dotenv()

REMONLINE_API_KEY_PROD = os.getenv('API_KEY_PROD')
DEFAULT_BRANCH_PROD = os.getenv('BRANCH_PROD')
PRICE_ID_PROD = os.getenv('PRICE_ID_PROD')
DB_PATH = os.getenv("DB_PATH")
BONUS_ID = os.getenv("BONUS_ID")
LOG_LEVEL = os.getenv("LOG_LEVEL")
DELETE_ORDER_STATUS_ID = os.getenv("DELETE_ORDER_STATUS_ID")
CATEGORIES_IGNORE_IDS = [753923]
