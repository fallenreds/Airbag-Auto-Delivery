from fastapi import APIRouter, HTTPException
from models import BaseTemplate, Template, ClientUpdate, BaseClientUpdate
from DB import DBConnection
import config
router = APIRouter(prefix='/clientupdates', tags=['Client Updates'])
from logger import logger

@router.get('/', response_model=list[ClientUpdate])
def get_client_updates()->list[ClientUpdate]:
    """Get all templates"""
    db = DBConnection(config.DB_PATH)
    response = db.get_client_updates()
    db.connection.close()
    return response

@router.get('/{client_update_id}', response_model=ClientUpdate)
def get_client_update(client_update_id:int)->ClientUpdate|None:
    """Get template by id"""
    db = DBConnection(config.DB_PATH)
    response = db.get_client_update(client_update_id)
    db.connection.close()
    if not response:
        raise HTTPException(404, 'Client update not found')
    return response

@router.delete('/{client_update_id}')
def delete_client_update(client_update_id:int)->None:
    """Delete template by id"""
    db = DBConnection(config.DB_PATH)
    db.delete_client_update(client_update_id)
    db.connection.close()


@router.post('/', response_model=ClientUpdate)
def create_client_update(client_update:BaseClientUpdate)->ClientUpdate:
    """Create new template"""
    db = DBConnection(config.DB_PATH)
    response = db.create_client_update(client_update)
    db.connection.close()
    return response