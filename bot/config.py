import os
from dotenv import load_dotenv

load_dotenv()

REMONLINE_API_KEY_PROD = os.getenv('API_KEY_PROD')
DEFAULT_BRANCH_PROD = os.getenv('BRANCH_PROD')
BOT_TOKEN = os.getenv('BOT_TOKEN')
WEB_URL = os.getenv('WEB_APP_URL')
PRICE_ID_PROD = os.getenv('PRICE_ID_PROD')
BASE_URL = os.getenv('BASE_URL')
LOCAL_PROXY_URL = os.getenv('LOCAL_PROXY_URL')
NOVA_POST_API_KEY = os.getenv('NOVA_POST_API_KEY')
BACKEND_API_KEY = os.getenv('BACKEND_API_KEY')