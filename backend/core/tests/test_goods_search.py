"""
Поиск товаров: без учёта регистра и по любым вхождениям.

SQLite сравнивает без учёта регистра только ASCII, поэтому `icontains` работал
на латинице и молча не работал на кириллице: «original» и «ORIGINAL» находили
одно и то же, а «пп» не находило «ПП сиденье» вовсе. Половина каталога назван
кириллицей, так что для покупателя поиск просто не работал.

Вторая половина проблемы: искалась вся строка целиком, поэтому «пп руль» не
находило «ПП в руль 60мм» — хотя оба слова в названии есть.
"""
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import Good, GoodCategory

HOST = {"HTTP_HOST": "testserver"}

TITLES = [
    "ПП в руль 60мм",
    "ПП сиденье/ноги 200мм",
    "Парашют 60мм",
    "ПП сиденье/ноги 110мм Original",
    "Ремінь безпеки передній",
]


def make_goods():
    # Категория обязательна: витрина не показывает осиротевшие товары.
    category = GoodCategory.objects.create(id_remonline=1, title="Подушки безпеки")
    for i, title in enumerate(TITLES, start=1):
        Good.objects.create(
            title=title, id_remonline=i, price_minor=100000, currency="UAH",
            category=category,
        )


class SearchFieldTests(TestCase):
    def test_search_title_is_filled_on_save(self):
        good = Good.objects.create(
            title="ПП в руль 60мм", id_remonline=1, price_minor=1000
        )

        self.assertEqual(good.search_title, "пп в руль 60мм")

    def test_search_title_follows_the_title(self):
        good = Good.objects.create(title="Старе", id_remonline=2, price_minor=1000)
        good.title = "Нове НАЗВАНИЕ"
        good.save()

        good.refresh_from_db()
        self.assertEqual(good.search_title, "нове название")


class SearchFilterTests(TestCase):
    def setUp(self):
        make_goods()

    def find(self, query):
        from core.filters.goods import GoodFilterSet

        return list(
            GoodFilterSet({"title__icontains": query}, queryset=Good.objects.all())
            .qs.values_list("title", flat=True)
        )

    # ── регистр ──────────────────────────────────────────────────────────────

    def test_cyrillic_lowercase_finds_uppercase(self):
        """Главный случай: раньше возвращалось пусто."""
        self.assertEqual(len(self.find("пп")), 3)

    def test_cyrillic_uppercase_finds_it_too(self):
        self.assertEqual(len(self.find("ПП")), 3)

    def test_mixed_case_works(self):
        self.assertEqual(len(self.find("Пп")), 3)

    def test_latin_still_works(self):
        self.assertEqual(len(self.find("original")), 1)
        self.assertEqual(len(self.find("ORIGINAL")), 1)

    # ── вхождения ────────────────────────────────────────────────────────────

    def test_substring_in_the_middle(self):
        self.assertEqual(len(self.find("сиденье")), 2)

    def test_several_words_are_joined_by_and(self):
        found = self.find("пп руль")

        self.assertEqual(found, ["ПП в руль 60мм"])

    def test_word_order_does_not_matter(self):
        self.assertEqual(self.find("руль пп"), ["ПП в руль 60мм"])

    def test_words_may_be_partial(self):
        self.assertEqual(self.find("ремін безп"), ["Ремінь безпеки передній"])

    def test_word_that_matches_nothing_excludes_everything(self):
        self.assertEqual(self.find("пп трактор"), [])

    def test_empty_query_returns_everything(self):
        self.assertEqual(len(self.find("   ")), len(TITLES))


class SearchThroughApiTests(TestCase):
    """
    Через API — потому что там два фильтра работают подряд, и второй когда-то
    мог отменить результат первого.
    """

    def setUp(self):
        make_goods()
        self.api = APIClient()

    def search(self, query):
        response = self.api.get("/api/v2/goods/", {"title__icontains": query}, **HOST)
        self.assertEqual(response.status_code, 200)
        return [row["title"] for row in response.data["results"]]

    def test_lowercase_cyrillic_search(self):
        self.assertEqual(len(self.search("пп")), 3)

    def test_multiword_search(self):
        self.assertEqual(self.search("пп руль"), ["ПП в руль 60мм"])

    def test_search_alias_works_too(self):
        response = self.api.get("/api/v2/goods/", {"search": "пп руль"}, **HOST)

        self.assertEqual([r["title"] for r in response.data["results"]], ["ПП в руль 60мм"])

    def test_other_filters_still_apply(self):
        """Проверка, что исключение параметра из общего фильтра не сломало прочие."""
        response = self.api.get("/api/v2/goods/", {"currency": "UAH"}, **HOST)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), len(TITLES))
