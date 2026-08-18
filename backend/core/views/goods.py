import hashlib
import random
from datetime import date, datetime

from django.core.cache import cache
from django.db.models import Case, CharField, IntegerField, Value, When
from django.db.models.functions import Cast, Concat, MD5
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.response import Response

from core.models import Good, GoodCategory
from core.serializers import GoodCategorySerializer, GoodSerializer

from .utils import generate_filterset_for_model


def in_stock_first():
    """Сначала товары в наличии, потом остальные."""
    return Case(
        When(residue__gt=0, then=Value(0)),
        default=Value(1),
        output_field=IntegerField(),
    )


def current_shuffle_bucket():
    """
    Метка 15-минутного интервала. Внутри одного интервала порядок товаров
    одинаков для всех запросов, поэтому листание страниц не дублирует и не
    теряет товары; раз в 15 минут витрина перемешивается заново.
    """
    now = datetime.now()
    return now.strftime("%Y-%m-%d-%H") + f"-{(now.minute // 15) * 15:02d}"


class GoodViewSet(viewsets.ModelViewSet):
    # Товары без категории в выдачу не попадают: категорию могли убрать из
    # вайтлиста, и товар остался осиротевшим (Good.category — SET_NULL). Такой
    # товар относится к скрытой категории, показывать его нельзя.
    # Основную чистку делает sync_goods, это страховка на уровне выдачи.
    queryset = (
        Good.objects.filter(category__isnull=False).order_by(in_stock_first())
    )
    serializer_class = GoodSerializer
    filterset_class = generate_filterset_for_model(Good)
    ordering_fields = ['price_minor', 'title', 'residue']

    def get_permissions(self):
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [AllowAny()]
        return [IsAdminUser()]

    def get_queryset(self):
        qs = super().get_queryset()

        # Витрина без явной сортировки перемешивается, но перемешивание должно
        # уживаться с limit/offset: случайный порядок на уровне БД (ORDER BY
        # random()) пересчитывается на каждый запрос, поэтому вторая страница
        # показывала бы товары с первой. Хешируем id вместе с меткой интервала —
        # порядок псевдослучайный, но стабильный, пока метка та же.
        if self.action == "list" and not self.request.query_params.get("ordering"):
            qs = qs.annotate(
                shuffle_key=MD5(
                    Concat(
                        Cast("id", output_field=CharField()),
                        Value(current_shuffle_bucket()),
                        output_field=CharField(),
                    )
                )
            ).order_by(in_stock_first(), "shuffle_key")

        return qs

    @action(detail=False, methods=["GET"], permission_classes=[AllowAny], url_path="featured")
    def featured(self, request):
        bucket = current_shuffle_bucket()
        cache_key = f"featured_goods:{bucket}"
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached)

        all_cats = list(GoodCategory.objects.all())
        cat_map = {c.id_remonline: {"local_id": c.id, "children": []} for c in all_cats}
        roots = []
        for c in all_cats:
            if c.parent_id is None:
                roots.append(c.id_remonline)
            elif c.parent_id in cat_map:
                cat_map[c.parent_id]["children"].append(c.id_remonline)

        def subtree_local_ids(rem_id):
            node = cat_map.get(rem_id)
            if node is None:
                return []
            result = [node["local_id"]]
            for child_rem in node["children"]:
                result.extend(subtree_local_ids(child_rem))
            return result

        seed = int(hashlib.md5(bucket.encode()).hexdigest(), 16) % (2**32)
        slots_per_cat = max(2, 12 // max(len(roots), 1))
        selected = []

        for rem_id in roots:
            local_ids = subtree_local_ids(rem_id)
            goods = list(Good.objects.filter(category_id__in=local_ids, residue__gt=0))
            rng = random.Random(seed ^ rem_id)
            rng.shuffle(goods)
            selected.extend(goods[:slots_per_cat])

        if len(selected) < 12:
            seen_ids = {g.id for g in selected}
            extra = list(
                Good.objects.filter(residue__gt=0, category__isnull=False)
                .exclude(id__in=seen_ids)
            )
            rng = random.Random(seed)
            rng.shuffle(extra)
            selected.extend(extra[:12 - len(selected)])

        serializer = GoodSerializer(selected[:12], many=True, context={"request": request})
        data = serializer.data
        cache.set(cache_key, data, timeout=900)  # 15 minutes
        return Response(data)


class GoodCategoryViewSet(viewsets.ModelViewSet):
    queryset = GoodCategory.objects.all()
    serializer_class = GoodCategorySerializer
    filterset_class = generate_filterset_for_model(GoodCategory)

    def get_permissions(self):
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [AllowAny()]
        return [IsAdminUser()]

    @swagger_auto_schema(
        method="get",
        operation_description="Возвращает дерево категорий",
        responses={
            200: openapi.Schema(
                type=openapi.TYPE_ARRAY,
                items=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "id": openapi.Schema(type=openapi.TYPE_INTEGER),
                        "id_remonline": openapi.Schema(type=openapi.TYPE_INTEGER),
                        "title": openapi.Schema(type=openapi.TYPE_STRING),
                        "slug": openapi.Schema(type=openapi.TYPE_STRING),
                        "image": openapi.Schema(type=openapi.TYPE_STRING),
                        "children": openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Schema(
                                type=openapi.TYPE_OBJECT
                            ),  # ← вот это важно
                        ),
                    },
                ),
            )
        },
    )
    @action(
        detail=False,
        methods=["GET"],
        permission_classes=[AllowAny],
        url_path="tree",
        pagination_class=None,
    )
    def tree(self, request):
        raw_categories = GoodCategory.objects.all()

        roots: list[dict] = []
        nodes: dict[int, dict] = {}

        for category in raw_categories:
            rem_id = category.id_remonline  # текущий remonline id
            parent_rem_id = category.parent_id  # remonline id родителя
            image_url = None
            if category.image:
                image_url = request.build_absolute_uri(category.image.url)


            node = nodes.get(rem_id)
            if node is None:
                node = {
                    "id": category.id,  # локальный id, если нужен
                    "id_remonline": rem_id,
                    "title": category.title,
                    "slug": category.slug,
                    "image": image_url,
                    "children": [],
                }
                nodes[rem_id] = node
            else:
                node["id"] = category.id
                node["id_remonline"] = rem_id
                node["title"] = category.title
                node["slug"] = category.slug
                node["image"] = image_url
                node.setdefault("children", [])

            if parent_rem_id is None:
                roots.append(node)
            else:
                parent = nodes.get(parent_rem_id)
                if parent is None:
                    parent = {
                        "id": None,
                        "id_remonline": parent_rem_id,
                        "title": "",
                        "slug": "",
                        "image": None,
                        "children": [],
                    }
                    nodes[parent_rem_id] = parent

                parent["children"].append(node)

        return Response(roots)
