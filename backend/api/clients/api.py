from fastapi import APIRouter

from DB import DBConnection
from config import DB_PATH
from loader import CRM
from models import ClientModel

router = APIRouter(tags=['Clients'])
@router.get("/client/{client_id}")
def get_client_by_id(client_id):
    db = DBConnection(DB_PATH)
    client = db.get_client_by_id(client_id)
    db.connection.close()
    return client

@router.post("/client/")
def get_or_post_client(client: ClientModel):
    client_data = CRM.find_or_create_client(client.phone, client.name)
    return client_data

@router.get("/clients/")
def get_all_clients():
    db = DBConnection(DB_PATH)
    response = db.get_all_clients()
    db.connection.close()
    return response