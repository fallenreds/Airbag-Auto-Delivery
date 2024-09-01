from fastapi import APIRouter, HTTPException
from models import BaseTemplate, Template
from DB import DBConnection
import config
router = APIRouter(prefix='/templates', tags=['Templates'])
from logger import logger

@router.get('/')
def get_templates()->list[Template]:
    """Get all templates"""
    db = DBConnection(config.DB_PATH)
    response = db.get_templates()
    db.connection.close()
    return response

@router.get('/{template_id}', response_model=Template)
def get_template(template_id:int)->Template|None:
    """Get template by id"""
    db = DBConnection(config.DB_PATH)
    response = db.get_template(template_id)
    db.connection.close()
    if not response:
        raise HTTPException(404, 'Template not found')
    return response

@router.delete('/{template_id}')
def delete_template(template_id:int)->None:
    """Delete template by id"""
    db = DBConnection(config.DB_PATH)
    db.delete_template(template_id)
    db.connection.close()


@router.post('/', response_model=Template)
def create_template(template:BaseTemplate)->Template:
    """Create new template"""
    db = DBConnection(config.DB_PATH)
    response = db.create_template(template)
    db.connection.close()
    return response