"""Товары из скрытых (не входящих в вайтлист) категорий не должны показываться."""

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from core.goods_sync import get_goods_ids_to_delete
from core.models import Good, GoodCategory


class OrphanGoodsDeletionTests(TestCase):
    """get_goods_ids_to_delete должен вычищать товары без валидной категории."""

    def setUp(self):
        self.valid_cat = GoodCategory.objects.create(
            id=754099, id_remonline=754099, title="Covers"
        )
        self.hidden_cat = GoodCategory.objects.create(
            id=999999, id_remonline=999999, title="Wheels"
        )

    def _good(self, rem_id, category):
        return Good.objects.create(
            id_remonline=rem_id, title=f"good-{rem_id}", category=category
        )

    def test_orphan_good_is_deleted(self):
        """Товар с category=NULL (категорию убрали из вайтлиста) удаляется."""
        orphan = self._good(61951359, self.hidden_cat)
        # Категорию убрали из вайтлиста — sync_categories её удалил,
        # FK с on_delete=SET_NULL обнулил category у товара.
        self.hidden_cat.delete()
        orphan.refresh_from_db()
        self.assertIsNone(orphan.category_id)

        ids = get_goods_ids_to_delete(
            existing_goods_qs=Good.objects.all(),
            remonline_good_ids={61951359},  # в Remonline товар ещё есть
            valid_category_ids_db={self.valid_cat.id},
        )

        self.assertEqual(ids, {61951359})

    def test_good_of_stale_category_is_deleted(self):
        """Товар, чья категория больше не входит в актуальный набор, удаляется."""
        self._good(777, self.hidden_cat)

        ids = get_goods_ids_to_delete(
            existing_goods_qs=Good.objects.all(),
            remonline_good_ids={777},
            valid_category_ids_db={self.valid_cat.id},
        )

        self.assertEqual(ids, {777})

    def test_good_missing_in_remonline_is_deleted(self):
        self._good(555, self.valid_cat)

        ids = get_goods_ids_to_delete(
            existing_goods_qs=Good.objects.all(),
            remonline_good_ids=set(),
            valid_category_ids_db={self.valid_cat.id},
        )

        self.assertEqual(ids, {555})

    def test_valid_good_is_kept(self):
        self._good(111, self.valid_cat)

        ids = get_goods_ids_to_delete(
            existing_goods_qs=Good.objects.all(),
            remonline_good_ids={111},
            valid_category_ids_db={self.valid_cat.id},
        )

        self.assertEqual(ids, set())


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
)
class OrphanGoodsApiVisibilityTests(TestCase):
    """Страховка на уровне выдачи: осиротевший товар не отдаётся API."""

    def setUp(self):
        self.api = APIClient()
        self.cat = GoodCategory.objects.create(
            id=754099, id_remonline=754099, title="Covers"
        )
        self.visible = Good.objects.create(
            id_remonline=1, title="visible", category=self.cat, residue=5
        )
        self.orphan = Good.objects.create(
            id_remonline=2, title="orphan", category=None, residue=5
        )

    def test_orphan_absent_from_list(self):
        resp = self.api.get("/api/v2/goods/")
        self.assertEqual(resp.status_code, 200)
        ids = [g["id"] for g in resp.json()["results"]]
        self.assertIn(self.visible.id, ids)
        self.assertNotIn(self.orphan.id, ids)

    def test_orphan_detail_returns_404(self):
        resp = self.api.get(f"/api/v2/goods/{self.orphan.id}/")
        self.assertEqual(resp.status_code, 404)

    def test_orphan_absent_from_featured(self):
        resp = self.api.get("/api/v2/goods/featured/")
        self.assertEqual(resp.status_code, 200)
        ids = [g["id"] for g in resp.json()]
        self.assertNotIn(self.orphan.id, ids)
