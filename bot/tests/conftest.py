"""
Shared fixtures for bot tests.

Sets required environment variables BEFORE any bot module is imported,
so that config.py reads correct values from os.environ.
Also stubs out aiogram 2.x-specific paths (bot uses 2.25.2 API which
differs from installed aiogram 3.x).
"""
import os
import sys
from types import ModuleType
from unittest.mock import MagicMock

# ── env vars (before any bot import) ────────────────────────────────────────
os.environ.setdefault("BOT_TOKEN", "1234567890:test_bot_token")
os.environ.setdefault("BACKEND_API_BASE", "http://testserver/")
os.environ.setdefault("BACKEND_API_KEY", "test-api-key")
os.environ.setdefault("NOVA_POST_API_KEY", "test-nova-key")
os.environ.setdefault("PRICE_ID_PROD", "price_test_001")
os.environ.setdefault("API_KEY_PROD", "test-remonline-key")
os.environ.setdefault("BRANCH_PROD", "1")
os.environ.setdefault("WEB_APP_URL", "http://localhost:3000")

# ── aiogram 2.x compatibility shim ──────────────────────────────────────────
# Bot uses aiogram 2.25.2 API paths; installed version is 3.x.
# Strategy: let aiogram 3.x load fully first, then patch in the missing 2.x
# sub-modules so that "from aiogram.utils.exceptions import ..." etc. work.
import aiogram          # trigger full 3.x load (so aiogram.utils is a real pkg)
import aiogram.utils    # ensure the real package is in sys.modules

# Patch aiogram.utils.exceptions (moved/removed in 3.x)
_exc = ModuleType("aiogram.utils.exceptions")
_exc.ChatNotFound = type("ChatNotFound", (Exception,), {})
_exc.BotBlocked   = type("BotBlocked",   (Exception,), {})
aiogram.utils.exceptions = _exc                         # type: ignore[attr-defined]
sys.modules["aiogram.utils.exceptions"] = _exc

# Patch aiogram.utils.callback_data (removed in 3.x)
_cb = ModuleType("aiogram.utils.callback_data")
_cb.CallbackData = MagicMock()
aiogram.utils.callback_data = _cb                       # type: ignore[attr-defined]
sys.modules["aiogram.utils.callback_data"] = _cb

# Patch aiogram.contrib.* (removed in 3.x)
for _mod_name in (
    "aiogram.contrib",
    "aiogram.contrib.fsm_storage",
    "aiogram.contrib.fsm_storage.memory",
):
    _m = ModuleType(_mod_name)
    _m.MemoryStorage = MagicMock()
    sys.modules[_mod_name] = _m

# ── bot package path ─────────────────────────────────────────────────────────
BOT_DIR = os.path.dirname(os.path.dirname(__file__))
if BOT_DIR not in sys.path:
    sys.path.insert(0, BOT_DIR)

import pytest
from aioresponses import aioresponses


BASE_URL = "http://testserver/"


@pytest.fixture
def mocked():
    """aioresponses context manager — intercepts all aiohttp requests."""
    with aioresponses() as m:
        yield m


# ── Reusable sample data ──────────────────────────────────────────────────────

@pytest.fixture
def sample_order():
    return {
        "id": 1,
        "name": "Іван",
        "last_name": "Іваненко",
        "phone": "+380501234567",
        "nova_post_address": "м. Київ, відд. 5",
        "prepayment": True,
        "is_paid": False,
        "ttn": None,
        "is_completed": False,
        "telegram_id": 111111,
        "remember_count": 0,
        "branch_remember_count": 0,
        "items": [],
        "grand_total_minor": 50000,
        "subtotal_minor": 50000,
        "discount_total_minor": 0,
        "discount_percent": None,
        "description": None,
        "date": "2025-01-01T10:00:00Z",
        "client": 1,
        "remonline_sync_status": "SYNCED",
        "remonline_order_id": None,
    }


@pytest.fixture
def sample_client():
    return {
        "id": 1,
        "name": "Іван",
        "last_name": "Іваненко",
        "phone": "+380501234567",
        "email": "ivan@test.com",
        "telegram_id": 111111,
        "is_staff": False,
        "is_guest": False,
        "nova_post_address": "м. Київ, відд. 5",
    }


@pytest.fixture
def paginated(sample_order):
    """Helper to build a DRF paginated response."""
    def _make(results, count=None):
        return {
            "count": count if count is not None else len(results),
            "next": None,
            "previous": None,
            "results": results,
        }
    return _make
