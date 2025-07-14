from fastapi import APIRouter, HTTPException
from models import BaseTemplate, Template, ClientUpdate, BaseClientUpdate
from DB import DBConnection
import config
router = APIRouter(prefix='/clientupdates', tags=['Client Updates'])
from logger import logger

@router.get('/', response_model=list[ClientUpdate])
def get_client_updates()->list[ClientUpdate]:
    """
    Получить все обновления всех клиентов
    Вероятно будет изменено в следующей версии API
    """
    db = DBConnection(config.DB_PATH)
    response = db.get_client_updates()
    db.connection.close()
    return response

@router.get('/{client_update_id}', response_model=ClientUpdate)
def get_client_update(client_update_id:int)->ClientUpdate|None:
    """
    Получить все обновление клиента по id
    Вероятно будет изменено в следующей версии API
    """
    db = DBConnection(config.DB_PATH)
    response = db.get_client_update(client_update_id)
    db.connection.close()
    if not response:
        raise HTTPException(404, 'Client update not found')
    return response

@router.delete('/{client_update_id}')
def delete_client_update(client_update_id:int)->None:
    """
    Удалить запить обновления по id - после каждого чтения обновления
    Вероятно будет изменено в следующей версии API
    """
    db = DBConnection(config.DB_PATH)
    db.delete_client_update(client_update_id)
    db.connection.close()


@router.post('/', response_model=ClientUpdate)
def create_client_update(client_update:BaseClientUpdate)->ClientUpdate:
    """
    Создает новое обновление клиента в системе
    Вероятно будет удалено в следующей версии API
    """
    db = DBConnection(config.DB_PATH)
    response = db.create_client_update(client_update)
    db.connection.close()
    return response