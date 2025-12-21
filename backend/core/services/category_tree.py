from typing import Iterable

from core.models import GoodCategory


def get_descendant_category_ids(root_ids: Iterable[int]) -> list[int]:
    """
    Возвращает id (PK) всех категорий-потомков (включая сами root_ids).

    Связь дерева:
      - GoodCategory.id           — локальный PK
      - GoodCategory.id_remonline — внешний ID
      - GoodCategory.parent_id    — id_remonline родителя
    То есть: child.parent_id == parent.id_remonline
    """
    root_ids = list({int(r) for r in root_ids if r is not None})
    if not root_ids:
        return []

    categories = list(GoodCategory.objects.all())

    # По PK
    by_id: dict[int, GoodCategory] = {c.id: c for c in categories}
    # По parent_id (id_remonline родителя)
    by_parent_rem_id: dict[int | None, list[GoodCategory]] = {}
    for c in categories:
        by_parent_rem_id.setdefault(c.parent_id, []).append(c)

    result: set[int] = set()
    stack: list[int] = root_ids.copy()  # всегда PK

    while stack:
        cid = stack.pop()
        if cid in result:
            continue
        result.add(cid)

        parent = by_id.get(cid)
        if not parent:
            continue

        # дети: parent_id == parent.id_remonline
        children = by_parent_rem_id.get(parent.id_remonline, [])
        stack.extend(child.id for child in children)  # кладём PK детей

    return list(result)