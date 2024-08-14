import os
from dotenv import load_dotenv

load_dotenv()

REMONLINE_API_KEY_PROD = os.getenv('API_KEY_PROD')
REMONLINE_API_KEY_TEST = os.getenv('API_KEY_TEST')

DEFAULT_BRANCH_PROD = os.getenv('BRANCH_PROD')
DEFAULT_BRANCH_TEST = os.getenv('BRANCH_TEST')

BOT_TOKEN = os.getenv('BOT_TOKEN')

WEB_URL = os.getenv('WEB_APP_URL')

PRICE_ID_TEST = os.getenv('PRICE_ID_TEST')
PRICE_ID_PROD = os.getenv('PRICE_ID_PROD')

BASE_URL = os.getenv('BASE_URL')
TEST_URL = os.getenv('TEST_URL')

NOVA_POST_API_KEY = os.getenv('NOVA_POST_API_KEY')