"""
Tests for bot/api.py — all 41 async functions.

Strategy:
  - aioresponses mocks every aiohttp call; no real network traffic.
  - Each function gets a success test (200/201/204) and a failure test (404/500→None).
  - Paginated endpoints (_fetch_paginated) are tested for single and multi-page responses.
"""
import pytest
from aioresponses import aioresponses

import api
from tests.conftest import BASE_URL


# ── helpers ───────────────────────────────────────────────────────────────────

def paged(results, next_url=None, count=None):
    return {
        "count": count if count is not None else len(results),
        "next": next_url,
        "previous": None,
        "results": results,
    }


ORDER = {
    "id": 1, "name": "Test", "last_name": "User", "phone": "+380501234567",
    "nova_post_address": "Kyiv, dep 1", "prepayment": True, "is_paid": False,
    "ttn": None, "is_completed": False, "telegram_id": 111111,
    "remember_count": 0, "branch_remember_count": 0, "items": [],
    "grand_total_minor": 10000, "subtotal_minor": 10000,
    "discount_total_minor": 0, "discount_percent": None,
    "description": None, "date": "2025-01-01T00:00:00Z",
    "client": 1, "remonline_sync_status": "SYNCED", "remonline_order_id": None,
}
CLIENT = {
    "id": 1, "name": "Test", "last_name": "User",
    "phone": "+380501234567", "email": "t@t.com", "telegram_id": 111111,
    "is_staff": False, "is_guest": False, "nova_post_address": "Kyiv",
}
TEMPLATE = {"id": 1, "name": "Promo", "text": "Hello!"}
DISCOUNT = {"id": 1, "percentage": "10.00", "month_payment": 100000}
VISITOR = {"id": 1, "telegram_id": 111111}
ORDER_EVENT = {"id": 1, "type": "CREATED_ADMIN_MESSAGE", "order": 1}
CLIENT_EVENT = {"id": 1, "type": "CREATED", "client": 1, "created_at": "2025-01-01T00:00:00Z"}
GOOD = {"id": 1, "title": "Airbag", "price_minor": 50000, "residue": 5}


# ══════════════════════════════════════════════════════════════════════════════
# _fetch_paginated
# ══════════════════════════════════════════════════════════════════════════════

class TestFetchPaginated:
    async def test_single_page(self, mocked):
        mocked.get(
            f"{BASE_URL}api/v2/orders/?limit=100&offset=0",
            payload=paged([ORDER]),
        )
        result = await api._fetch_paginated("api/v2/orders/")
        assert result == [ORDER]

    async def test_two_pages(self, mocked):
        order2 = {**ORDER, "id": 2}
        mocked.get(
            f"{BASE_URL}api/v2/orders/?limit=100&offset=0",
            payload=paged([ORDER], next_url=f"{BASE_URL}api/v2/orders/?limit=100&offset=100"),
        )
        mocked.get(
            f"{BASE_URL}api/v2/orders/?limit=100&offset=100",
            payload=paged([order2]),
        )
        result = await api._fetch_paginated("api/v2/orders/")
        assert len(result) == 2
        assert result[0]["id"] == 1
        assert result[1]["id"] == 2

    async def test_limit_respected(self, mocked):
        orders = [{"id": i} for i in range(5)]
        mocked.get(
            f"{BASE_URL}api/v2/orders/?limit=100&offset=0",
            payload=paged(orders),
        )
        result = await api._fetch_paginated("api/v2/orders/", limit=3)
        assert len(result) == 3

    async def test_server_error_returns_empty(self, mocked):
        mocked.get(f"{BASE_URL}api/v2/orders/?limit=100&offset=0", status=500)
        result = await api._fetch_paginated("api/v2/orders/")
        assert result == []

    async def test_with_query_params(self, mocked):
        mocked.get(
            f"{BASE_URL}api/v2/orders?telegram_id=111&limit=100&offset=0",
            payload=paged([ORDER]),
        )
        result = await api._fetch_paginated("api/v2/orders?telegram_id=111")
        assert result == [ORDER]


# ══════════════════════════════════════════════════════════════════════════════
# Orders
# ══════════════════════════════════════════════════════════════════════════════

class TestOrders:
    async def test_get_orders_by_tg_id_returns_list(self, mocked):
        mocked.get(
            f"{BASE_URL}api/v2/orders?telegram_id=111111&limit=100&offset=0",
            payload=paged([ORDER]),
        )
        result = await api.get_orders_by_tg_id(111111)
        assert isinstance(result, list)
        assert result[0]["id"] == 1

    async def test_get_active_orders_uses_pagination(self, mocked):
        mocked.get(
            f"{BASE_URL}api/v2/orders?is_completed=0&ordering=-date&limit=100&offset=0",
            payload=paged([ORDER]),
        )
        result = await api.get_active_orders()
        assert result == [ORDER]

    async def test_active_orders_are_requested_newest_first(self, mocked):
        """Админ смотрит список сверху вниз — свежий заказ должен быть первым."""
        mocked.get(
            f"{BASE_URL}api/v2/orders?is_completed=0&ordering=-date&limit=100&offset=0",
            payload=paged([ORDER]),
        )
        await api.get_active_orders()
        requested = [str(key[1]) for key in mocked.requests]
        assert any("ordering=-date" in url for url in requested), requested

    async def test_get_active_orders_by_telegram_id_returns_list(self, mocked):
        mocked.get(
            f"{BASE_URL}api/v2/orders?is_completed=0&telegram_id=111111&limit=100&offset=0",
            payload=paged([ORDER]),
        )
        result = await api.get_active_orders_by_telegram_id(111111)
        assert isinstance(result, list)
        assert result[0]["is_completed"] is False

    async def test_get_order_by_id_success(self, mocked):
        mocked.get(f"{BASE_URL}api/v2/orders/1/", payload=ORDER)
        result = await api.get_order_by_id(1)
        assert result["id"] == 1

    async def test_get_order_by_id_not_found(self, mocked):
        mocked.get(f"{BASE_URL}api/v2/orders/999/", status=404)
        result = await api.get_order_by_id(999)
        assert result is None

    async def test_get_order_by_ttn_returns_first(self, mocked):
        mocked.get(
            f"{BASE_URL}api/v2/orders?ttn=20450000001234&limit=100&offset=0",
            payload=paged([ORDER]),
        )
        result = await api.get_order_by_ttn("20450000001234")
        assert result["id"] == 1

    async def test_get_order_by_ttn_not_found(self, mocked):
        mocked.get(
            f"{BASE_URL}api/v2/orders?ttn=UNKNOWN&limit=100&offset=0",
            payload=paged([]),
        )
        result = await api.get_order_by_ttn("UNKNOWN")
        assert result is None

    async def test_delete_order_success(self, mocked):
        mocked.delete(f"{BASE_URL}api/v2/orders/1/", status=204)
        result = await api.delete_order(1)
        assert result is True

    async def test_delete_order_not_found(self, mocked):
        mocked.delete(f"{BASE_URL}api/v2/orders/999/", status=404)
        result = await api.delete_order(999)
        assert result is None

    async def test_cancel_order_success(self, mocked):
        canceled = {**ORDER, "cancel_state": "canceled"}
        mocked.post(f"{BASE_URL}api/v2/orders/1/cancel/", payload=canceled)
        ok, data = await api.cancel_order(1, "changed_mind")
        assert ok is True
        assert data["cancel_state"] == "canceled"

    async def test_cancel_order_conflict_returns_code(self, mocked):
        """409 від бекенда несе код блокування — бот показує його клієнту."""
        mocked.post(
            f"{BASE_URL}api/v2/orders/1/cancel/",
            status=409,
            payload={"detail": "Cancellation is not allowed", "code": "order_shipped"},
        )
        ok, data = await api.cancel_order(1, "changed_mind")
        assert ok is False
        assert data["code"] == "order_shipped"

    async def test_request_cancel_order_success(self, mocked):
        requested = {**ORDER, "cancel_state": "requested"}
        mocked.post(f"{BASE_URL}api/v2/orders/1/request-cancel/", payload=requested)
        ok, data = await api.request_cancel_order(1, "changed_mind")
        assert ok is True
        assert data["cancel_state"] == "requested"

    async def test_approve_cancel_order_success(self, mocked):
        refunded = {**ORDER, "cancel_state": "canceled", "refund_state": "pending"}
        mocked.post(f"{BASE_URL}api/v2/orders/1/cancel-approve/", payload=refunded)
        ok, data = await api.approve_cancel_order(1)
        assert ok is True
        assert data["refund_state"] == "pending"

    async def test_reject_cancel_order_success(self, mocked):
        rejected = {**ORDER, "cancel_state": "rejected"}
        mocked.post(f"{BASE_URL}api/v2/orders/1/cancel-reject/", payload=rejected)
        ok, data = await api.reject_cancel_order(1, "товар зарезервовано")
        assert ok is True
        assert data["cancel_state"] == "rejected"

    async def test_mark_order_refunded_success(self, mocked):
        refunded = {**ORDER, "refund_state": "manual"}
        mocked.post(f"{BASE_URL}api/v2/orders/1/mark-refunded/", payload=refunded)
        ok, data = await api.mark_order_refunded(1)
        assert ok is True
        assert data["refund_state"] == "manual"

    async def test_make_pay_order_success(self, mocked):
        paid_order = {**ORDER, "is_paid": True}
        mocked.patch(f"{BASE_URL}api/v2/orders/1/", payload=paid_order)
        result = await api.make_pay_order(1)
        assert result["is_paid"] is True

    async def test_make_pay_order_failure(self, mocked):
        mocked.patch(f"{BASE_URL}api/v2/orders/1/", status=400)
        result = await api.make_pay_order(1)
        assert result is None

    async def test_finish_order(self, mocked):
        done_order = {**ORDER, "is_completed": True}
        mocked.patch(f"{BASE_URL}api/v2/orders/1/", payload=done_order)
        result = await api.finish_order(1)
        assert result["is_completed"] is True

    async def test_update_ttn(self, mocked):
        updated = {**ORDER, "ttn": "20450000001234"}
        mocked.patch(f"{BASE_URL}api/v2/orders/1/", payload=updated)
        result = await api.update_ttn(1, "20450000001234")
        assert result["ttn"] == "20450000001234"

    async def test_change_to_not_prepayment(self, mocked):
        updated = {**ORDER, "prepayment": False}
        mocked.patch(f"{BASE_URL}api/v2/orders/1/", payload=updated)
        result = await api.change_to_not_prepayment(1)
        assert result["prepayment"] is False

    async def test_update_no_paid_remember_count(self, mocked):
        updated = {**ORDER, "remember_count": 1}
        mocked.patch(f"{BASE_URL}api/v2/orders/1/", payload=updated)
        result = await api.update_no_paid_remember_count(1, 1)
        assert result["remember_count"] == 1

    async def test_update_branch_remember_count_increments(self, mocked):
        # First call: GET order (current branch_remember_count=0)
        mocked.get(f"{BASE_URL}api/v2/orders/1/", payload=ORDER)
        # Second call: PATCH with branch_remember_count=1
        updated = {**ORDER, "branch_remember_count": 1}
        mocked.patch(f"{BASE_URL}api/v2/orders/1/", payload=updated)
        result = await api.update_branch_remember_count(1)
        assert result["branch_remember_count"] == 1

    async def test_update_branch_remember_count_order_missing(self, mocked):
        mocked.get(f"{BASE_URL}api/v2/orders/999/", status=404)
        result = await api.update_branch_remember_count(999)
        assert result is None

    async def test_unpaid_overdue(self, mocked):
        mocked.get(
            f"{BASE_URL}api/v2/orders/unpaid-overdue/?limit=100&offset=0",
            payload=paged([ORDER]),
        )
        result = await api.unpaid_overdue()
        assert result == [ORDER]

    async def test_merge_order_success(self, mocked):
        merged = {**ORDER, "id": 99}
        mocked.post(
            f"{BASE_URL}api/v2/orders/merge/",
            payload=merged,
        )
        result = await api.merge_order(1, 2)
        assert result["id"] == 99

    async def test_merge_order_returns_none_on_error(self, mocked):
        mocked.post(f"{BASE_URL}api/v2/orders/merge/", status=400)
        result = await api.merge_order(1, 2)
        assert result is None


# ══════════════════════════════════════════════════════════════════════════════
# Order Events
# ══════════════════════════════════════════════════════════════════════════════

class TestOrderEvents:
    async def test_get_order_updates(self, mocked):
        mocked.get(
            f"{BASE_URL}api/v2/order-events/?limit=100&offset=0",
            payload=paged([ORDER_EVENT]),
        )
        result = await api.get_order_updates()
        assert result == [ORDER_EVENT]

    async def test_delete_order_updates_204(self, mocked):
        mocked.delete(f"{BASE_URL}api/v2/order-events/1/", status=204)
        result = await api.delete_order_updates(1)
        assert result is True

    async def test_delete_order_updates_not_found(self, mocked):
        mocked.delete(f"{BASE_URL}api/v2/order-events/99/", status=404)
        result = await api.delete_order_updates(99)
        assert result is None


# ══════════════════════════════════════════════════════════════════════════════
# Clients
# ══════════════════════════════════════════════════════════════════════════════

class TestClients:
    async def test_get_all_clients(self, mocked):
        mocked.get(
            f"{BASE_URL}api/v2/clients/?limit=100&offset=0",
            payload=paged([CLIENT]),
        )
        result = await api.get_all_clients()
        assert result == [CLIENT]

    async def test_get_client_by_id_success(self, mocked):
        mocked.get(f"{BASE_URL}api/v2/clients/1/", payload=CLIENT)
        result = await api.get_client_by_id(1)
        assert result["id"] == 1

    async def test_get_client_by_id_not_found(self, mocked):
        mocked.get(f"{BASE_URL}api/v2/clients/999/", status=404)
        result = await api.get_client_by_id(999)
        assert result is None

    async def test_get_client_by_tg_id_returns_paginated_dict(self, mocked):
        mocked.get(
            f"{BASE_URL}api/v2/clients?telegram_id=111111",
            payload={"count": 1, "next": None, "previous": None, "results": [CLIENT]},
        )
        result = await api.get_client_by_tg_id(111111)
        assert result["count"] == 1
        assert result["results"][0]["telegram_id"] == 111111

    async def test_get_client_by_tg_id_not_found(self, mocked):
        mocked.get(
            f"{BASE_URL}api/v2/clients?telegram_id=999999",
            payload={"count": 0, "next": None, "previous": None, "results": []},
        )
        result = await api.get_client_by_tg_id(999999)
        assert result["count"] == 0

    async def test_get_discount(self, mocked):
        discount_info = {"discount_percentage": 10, "current_month_spending": 50000}
        mocked.get(f"{BASE_URL}api/v2/clients/1/discount-info/", payload=discount_info)
        result = await api.get_discount(1)
        assert result["discount_percentage"] == 10

    async def test_get_discount_percentage(self, mocked):
        mocked.get(
            f"{BASE_URL}api/v2/clients/1/discount-info/",
            payload={"discount_percentage": 15, "current_month_spending": 100000},
        )
        result = await api.get_discount_percentage(1)
        assert result == 15

    async def test_get_discount_percentage_server_error_returns_zero(self, mocked):
        mocked.get(f"{BASE_URL}api/v2/clients/1/discount-info/", status=500)
        result = await api.get_discount_percentage(1)
        assert result == 0

    async def test_get_money_spend_cur_month(self, mocked):
        mocked.get(
            f"{BASE_URL}api/v2/clients/1/current-month-spending/",
            payload={"total_spending": 75000},
        )
        result = await api.get_money_spend_cur_month(1)
        assert result["total_spending"] == 75000

    async def test_add_bonus_client_discount_success(self, mocked):
        mocked.post(
            f"{BASE_URL}api/v2/clients/1/add-bonus/",
            payload={"success": True, "client": CLIENT},
        )
        result = await api.add_bonus_client_discount(1, 5)
        assert result["success"] is True

    async def test_add_bonus_client_discount_error(self, mocked):
        mocked.post(f"{BASE_URL}api/v2/clients/1/add-bonus/", status=400)
        result = await api.add_bonus_client_discount(1, 5)
        assert result is None


# ══════════════════════════════════════════════════════════════════════════════
# check_auth
# ══════════════════════════════════════════════════════════════════════════════

class TestCheckAuth:
    async def test_authenticated_user(self, mocked):
        mocked.get(
            f"{BASE_URL}api/v2/clients?telegram_id=111111",
            payload={"count": 1, "next": None, "previous": None, "results": [CLIENT]},
        )
        result = await api.check_auth(111111)
        assert result == {"success": True}

    async def test_unauthenticated_user(self, mocked):
        mocked.get(
            f"{BASE_URL}api/v2/clients?telegram_id=999999",
            payload={"count": 0, "next": None, "previous": None, "results": []},
        )
        result = await api.check_auth(999999)
        assert result == {"success": False}

    async def test_server_error_returns_failure(self, mocked):
        mocked.get(f"{BASE_URL}api/v2/clients?telegram_id=111111", status=500)
        result = await api.check_auth(111111)
        assert result == {"success": False}


# ══════════════════════════════════════════════════════════════════════════════
# Bot Visitors
# ══════════════════════════════════════════════════════════════════════════════

class TestBotVisitors:
    async def test_add_new_visitor_201(self, mocked):
        mocked.post(f"{BASE_URL}api/v2/bot-visitors/", status=201, payload=VISITOR)
        result = await api.add_new_visitor(111111)
        assert result["telegram_id"] == 111111

    async def test_add_new_visitor_200(self, mocked):
        mocked.post(f"{BASE_URL}api/v2/bot-visitors/", status=200, payload=VISITOR)
        result = await api.add_new_visitor(111111)
        assert result is not None

    async def test_add_new_visitor_duplicate_400(self, mocked):
        mocked.post(f"{BASE_URL}api/v2/bot-visitors/", status=400)
        result = await api.add_new_visitor(111111)
        assert result is None

    async def test_get_visitors(self, mocked):
        mocked.get(
            f"{BASE_URL}api/v2/bot-visitors/?limit=100&offset=0",
            payload=paged([VISITOR]),
        )
        result = await api.get_visitors()
        assert result == [VISITOR]

    async def test_delete_visitor_204(self, mocked):
        mocked.delete(f"{BASE_URL}api/v2/bot-visitors/1/", status=204)
        result = await api.delete_visitor(1)
        assert result is True

    async def test_delete_visitor_not_found(self, mocked):
        mocked.delete(f"{BASE_URL}api/v2/bot-visitors/99/", status=404)
        result = await api.delete_visitor(99)
        assert result is None


# ══════════════════════════════════════════════════════════════════════════════
# link_account_via_code
# ══════════════════════════════════════════════════════════════════════════════

class TestLinkAccountViaCode:
    async def test_success(self, mocked):
        mocked.post(
            f"{BASE_URL}api/v2/telegram/link/consume/",
            payload={"message": "Акаунт прив'язано"},
            status=200,
        )
        ok, msg = await api.link_account_via_code("ABC123", 111111)
        assert ok is True
        assert "прив'язано" in msg

    async def test_invalid_code(self, mocked):
        mocked.post(
            f"{BASE_URL}api/v2/telegram/link/consume/",
            payload={"detail": "Код недійсний"},
            status=400,
        )
        ok, msg = await api.link_account_via_code("WRONG", 111111)
        assert ok is False
        assert msg  # some error message returned

    async def test_network_error_returns_false(self, mocked):
        mocked.post(
            f"{BASE_URL}api/v2/telegram/link/consume/",
            exception=Exception("Connection refused"),
        )
        ok, msg = await api.link_account_via_code("X", 111111)
        assert ok is False
        assert msg


# ══════════════════════════════════════════════════════════════════════════════
# Discounts
# ══════════════════════════════════════════════════════════════════════════════

class TestDiscounts:
    async def test_get_discounts_info(self, mocked):
        mocked.get(
            f"{BASE_URL}api/v2/discounts/?limit=100&offset=0",
            payload=paged([DISCOUNT]),
        )
        result = await api.get_discounts_info()
        assert result == [DISCOUNT]

    async def test_post_discount_201(self, mocked):
        mocked.post(f"{BASE_URL}api/v2/discounts/", status=201, payload=DISCOUNT)
        result = await api.post_discount(10, 100000)
        assert result["percentage"] == "10.00"

    async def test_post_discount_200(self, mocked):
        mocked.post(f"{BASE_URL}api/v2/discounts/", status=200, payload=DISCOUNT)
        result = await api.post_discount(10, 100000)
        assert result is not None

    async def test_post_discount_failure(self, mocked):
        mocked.post(f"{BASE_URL}api/v2/discounts/", status=400)
        result = await api.post_discount(10, 100000)
        assert result is None

    async def test_delete_discount_204(self, mocked):
        mocked.delete(f"{BASE_URL}api/v2/discounts/1/", status=204)
        result = await api.delete_discount(1)
        assert result is True

    async def test_delete_discount_not_found(self, mocked):
        mocked.delete(f"{BASE_URL}api/v2/discounts/99/", status=404)
        result = await api.delete_discount(99)
        assert result is None


# ══════════════════════════════════════════════════════════════════════════════
# Goods
# ══════════════════════════════════════════════════════════════════════════════

class TestGoods:
    async def test_get_all_goods(self, mocked):
        mocked.get(
            f"{BASE_URL}api/v2/goods/?limit=100&offset=0",
            payload=paged([GOOD]),
        )
        result = await api.get_all_goods()
        assert result == [GOOD]

    async def test_get_all_goods_with_limit(self, mocked):
        goods = [{"id": i, "title": f"G{i}", "price_minor": 1000, "residue": 1} for i in range(5)]
        mocked.get(
            f"{BASE_URL}api/v2/goods/?limit=100&offset=0",
            payload=paged(goods),
        )
        result = await api.get_all_goods(limit=3)
        assert len(result) == 3


# ══════════════════════════════════════════════════════════════════════════════
# Templates
# ══════════════════════════════════════════════════════════════════════════════

class TestTemplates:
    async def test_get_templates(self, mocked):
        mocked.get(
            f"{BASE_URL}api/v2/templates/?limit=100&offset=0",
            payload=paged([TEMPLATE]),
        )
        result = await api.get_templates()
        assert result == [TEMPLATE]

    async def test_get_template_success(self, mocked):
        mocked.get(f"{BASE_URL}api/v2/templates/1/", payload=TEMPLATE)
        result = await api.get_template(1)
        assert result["name"] == "Promo"

    async def test_get_template_not_found(self, mocked):
        mocked.get(f"{BASE_URL}api/v2/templates/99/", status=404)
        result = await api.get_template(99)
        assert result is None

    async def test_create_template_201(self, mocked):
        mocked.post(f"{BASE_URL}api/v2/templates/", status=201, payload=TEMPLATE)
        result = await api.create_template("Promo", "Hello!")
        assert result["name"] == "Promo"

    async def test_create_template_error_returns_none(self, mocked):
        mocked.post(f"{BASE_URL}api/v2/templates/", status=400)
        result = await api.create_template("", "")
        assert result is None

    async def test_delete_template_204(self, mocked):
        mocked.delete(f"{BASE_URL}api/v2/templates/1/", status=204)
        result = await api.delete_template(1)
        assert result is True

    async def test_delete_template_not_found(self, mocked):
        mocked.delete(f"{BASE_URL}api/v2/templates/99/", status=404)
        result = await api.delete_template(99)
        assert result is None


# ══════════════════════════════════════════════════════════════════════════════
# Client Events
# ══════════════════════════════════════════════════════════════════════════════

class TestClientEvents:
    async def test_get_clients_updates(self, mocked):
        mocked.get(
            f"{BASE_URL}api/v2/client-events/?limit=100&offset=0",
            payload=paged([CLIENT_EVENT]),
        )
        result = await api.get_clients_updates()
        assert result == [CLIENT_EVENT]

    async def test_get_client_update_success(self, mocked):
        mocked.get(f"{BASE_URL}api/v2/client-events/1/", payload=CLIENT_EVENT)
        result = await api.get_client_update(1)
        assert result["type"] == "CREATED"

    async def test_get_client_update_not_found(self, mocked):
        mocked.get(f"{BASE_URL}api/v2/client-events/99/", status=404)
        result = await api.get_client_update(99)
        assert result is None

    async def test_delete_client_update_204(self, mocked):
        mocked.delete(f"{BASE_URL}api/v2/client-events/1/", status=204)
        result = await api.delete_client_update(1)
        assert result is True

    async def test_delete_client_update_not_found(self, mocked):
        mocked.delete(f"{BASE_URL}api/v2/client-events/99/", status=404)
        result = await api.delete_client_update(99)
        assert result is None


# ══════════════════════════════════════════════════════════════════════════════
# Nova Poshta
# ══════════════════════════════════════════════════════════════════════════════

class TestTtnTracking:
    async def test_success(self, mocked):
        np_response = {
            "success": True,
            "data": [{
                "Number": "20450000001234",
                "Status": "Прибув у відділення",
                "StatusCode": "7",
                "FactualWeight": "1",
                "RecipientFullName": "Іваненко Іван",
                "SenderFullNameEW": "Гекало Дмитро",
                "CityRecipient": "Київ",
                "WarehouseRecipient": "Відділення №5",
                "CitySender": "Харків",
                "WarehouseSender": "Відділення №1",
                "ScheduledDeliveryDate": "02.01.2025",
                "RecipientDateTime": "",
                "DocumentCost": "45",
                "AnnouncedPrice": "500",
                "PaymentMethod": "Cash",
                "ExpressWaybillAmountToPay": "0",
                "ExpressWaybillPaymentStatus": "Payed",
            }],
        }
        mocked.post("https://api.novaposhta.ua/v2.0/json/", payload=np_response)
        result = await api.ttn_tracking("20450000001234", "+380501234567")
        assert result["success"] is True
        assert result["data"][0]["Number"] == "20450000001234"

    async def test_server_error(self, mocked):
        mocked.post("https://api.novaposhta.ua/v2.0/json/", status=500)
        result = await api.ttn_tracking("20450000001234", "+380501234567")
        assert result is None


class TestPaymentMode:
    async def test_get_payment_mode(self, mocked):
        mocked.get(f"{BASE_URL}api/v2/payments/mode/", payload={"mode": "test"})
        result = await api.get_payment_mode()
        assert result["mode"] == "test"

    async def test_get_payment_mode_failure(self, mocked):
        mocked.get(f"{BASE_URL}api/v2/payments/mode/", status=403)
        result = await api.get_payment_mode()
        assert result is None

    async def test_set_payment_mode_success(self, mocked):
        mocked.patch(
            f"{BASE_URL}api/v2/payments/mode/", payload={"mode": "production"}
        )
        result = await api.set_payment_mode("production")
        assert result["mode"] == "production"
        assert "error" not in result

    async def test_set_payment_mode_surfaces_backend_detail(self, mocked):
        # Бэкенд объясняет, почему боевой режим включить нельзя — админ должен
        # увидеть именно эту причину, а не общее «не вдалося».
        detail = "MONOBANK_TOKEN_PROD збігається з тестовим токеном"
        mocked.patch(
            f"{BASE_URL}api/v2/payments/mode/", status=400, payload={"detail": detail}
        )
        result = await api.set_payment_mode("production")
        assert result["error"] == detail

    async def test_set_payment_mode_without_detail_falls_back_to_status(self, mocked):
        mocked.patch(f"{BASE_URL}api/v2/payments/mode/", status=500, body="boom")
        result = await api.set_payment_mode("production")
        assert result["error"] == "HTTP 500"
