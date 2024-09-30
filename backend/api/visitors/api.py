import logging

from fastapi import APIRouter

from DB import DBConnection
from config import DB_PATH
from loader import CRM
from models import ClientModel

router = APIRouter(prefix='/visitors' ,tags=['Visitors'])
@router.get("/api/v1/visitors/")
def get_visitors():
    db = DBConnection(DB_PATH)
    response = db.get_visitors()
    db.connection.close()
    return response


@router.post("/{telegram_id}")
def add_new_visitor(telegram_id):
    db = DBConnection(DB_PATH)
    response = db.post_new_visitor(telegram_id)
    db.connection.close()
    return response

@router.delete("/{telegram_id}")
def delete_visitor(telegram_id:int):
    db = DBConnection(DB_PATH)
    response = db.delete_visitor(telegram_id)
    db.connection.close()
    logging.info('Delete visitor')
    return response