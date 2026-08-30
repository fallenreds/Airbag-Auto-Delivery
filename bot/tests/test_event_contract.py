"""
Контракт кодов событий между бэкендом и ботом.

Бэкенд кладёт в очередь строку, бот разбирает её точным совпадением. Промах в
одну букву — и сообщение молча теряется: событие вычитывается из очереди и
удаляется, никто ничего не получает. Так годами не работали CREATED_ADMIN_MESSAGE,
CREATED_CLIENT_MESSAGE и PAYMENT_CONFIRMED — коды были объявлены, обработчики
написаны, а связь между ними никто не проверял.

Здесь связь проверяется: коды читаются прямо из моделей Django (текстом, без
импорта — у бота нет ни Django, ни его настроек) и сверяются с ключами
маршрутизации в `updates.py`.
"""
import ast
import pathlib

import pytest

import updates

MODELS = pathlib.Path(__file__).resolve().parents[2] / "backend" / "core" / "models.py"


def declared_codes(class_name):
    """Строковые константы класса `class_name` из models.py, кроме CHOICES."""
    tree = ast.parse(MODELS.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return {
                stmt.value.value
                for stmt in node.body
                if isinstance(stmt, ast.Assign)
                and isinstance(stmt.value, ast.Constant)
                and isinstance(stmt.value.value, str)
            }
    raise AssertionError(f"класс {class_name} не найден в {MODELS}")


def test_models_file_is_where_we_think_it_is():
    assert MODELS.exists(), f"не нашёл модели бэкенда по пути {MODELS}"


@pytest.mark.parametrize("class_name,handlers", [
    ("OrderEventType", "ORDER_EVENT_HANDLERS"),
    ("ClientEventType", "CLIENT_EVENT_HANDLERS"),
])
def test_every_backend_code_has_a_handler(class_name, handlers):
    """Событие, которое бэкенд умеет создать, обязано куда-то приводить."""
    missing = declared_codes(class_name) - set(getattr(updates, handlers))
    assert not missing, (
        f"{class_name}: бэкенд создаёт эти события, а бот их выбросит: {sorted(missing)}"
    )


@pytest.mark.parametrize("class_name,handlers", [
    ("OrderEventType", "ORDER_EVENT_HANDLERS"),
    ("ClientEventType", "CLIENT_EVENT_HANDLERS"),
])
def test_no_handler_waits_for_a_code_nobody_sends(class_name, handlers):
    """Обратная сторона: обработчик под несуществующий код — мёртвый код."""
    extra = set(getattr(updates, handlers)) - declared_codes(class_name)
    assert not extra, (
        f"{class_name}: бот ждёт события, которых бэкенд не создаёт: {sorted(extra)}"
    )
