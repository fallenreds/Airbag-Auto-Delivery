from fastapi import APIRouter, HTTPException
from pydantic import PositiveInt
from models import CartModel, UpdateCountModel
from DB import DBConnection
import config
router = APIRouter(prefix='/shoppingcart', tags=['Templates'])


@router.get("/{id}")
def get_shopping_cart(id: int):
    """
    Получить корзину покупок по ID
    Будет изменено в следующей версии API
    """
    db = DBConnection(config.DB_PATH)
    data = db.list_shopping_cart(id)
    db.connection.close()
    return data


@router.delete("/{id}")
def delete_shopping_cart(id: PositiveInt):
    """
    Удалить запись корзины по ID
    Будет изменено в следующей версии API
    """
    db = DBConnection(config.DB_PATH)
    db.delete_shopping_cart(id)
    db.connection.close()


@router.post("")
def post_shopping_cart(Cart: CartModel):
    """
    Создать запись в корзине
    Будет изменено в следующей версии API
    """
    new_cart = {
        "telegram_id": int(Cart.telegram_id),
        "good_id": int(Cart.good_id),
        "count": 1
    }
    db = DBConnection(config.DB_PATH)
    db.post_shopping_cart(new_cart["telegram_id"], new_cart["good_id"])
    db.connection.close()


@router.patch("/{id}")
def update_shopping_cart_count(id: int, CountModel: UpdateCountModel):
    """
    Обновить количество товаров в корзине по ID
    """
    db = DBConnection(config.DB_PATH)
    db.update_shopping_cart_count(id, CountModel.count)
    db.connection.close()