from fastapi import APIRouter

from DB import DBConnection
from config import DB_PATH
from loader import CRM
from models import ClientModel, ClientFullModel, SignInModel, BaseClientUpdate

router = APIRouter(tags=['Auth'])

@router.get("/isauthendicated/{telegram_id}")
def isauthenticated(telegram_id: int):
    """
    Проверка на то, существует ли пользователь с таким телеграм
    Будет изменено в след API версии
    """
    db = DBConnection(DB_PATH)
    client = db.get_client_by_telegram_id(telegram_id)
    if client:
        client_data = dict(client)
        return {
            "success": True,
            "id": client_data["id"],
            "id_remonline": client_data["id_remonline"],
            "name": client_data["name"],
            "last_name": client_data["last_name"],
            "phone": client_data["phone"]
        }
    else:
        return {"success": False}


@router.post("/singup/")
def create_client(client_data: ClientFullModel):
    """
    Cоздание нового клиента в системе и в Remonline
    В след версии API будет расширено другими значениями
    """
    remoline_client = CRM.find_or_create_client(client_data.phone, f"{client_data.name} {client_data.last_name}")
    print(client_data)

    if remoline_client is not None:
        db = DBConnection(DB_PATH)
        client = db.post_client(
            id_remonline=remoline_client["data"][0]["id"],
            telegram_id=str(client_data.telegram_id),
            name=client_data.name,
            last_name=client_data.last_name,
            login=client_data.login,
            password=client_data.password,
            phone=client_data.phone)

        db.create_client_update(BaseClientUpdate(type="CREATED", client_id=client))
        db.connection.close()
        return client
    return False


@router.get("/checkfreelogin/{login}")
def check_free_login(login: str):
    """
    Проверка на то, свободен ли логин
    В след версии API не будет изменено (вероятно поменяется ендпоинт-url)
    """
    db = DBConnection(DB_PATH)
    client = db.get_client_by_login(login)
    db.connection.close()

    if not client:
        return True
    else:
        return False


@router.get("/checkfreephone/{phone}")
def check_free_phone(phone: str):
    """
    Проверка на то, свободен ли телефон
    В след версии API не будет изменено (вероятно поменяется ендпоинт-url)
    """
    db = DBConnection(DB_PATH)
    client = db.get_client_by_phone(phone)
    db.connection.close()

    if not client:
        return True
    else:
        return False


@router.post("/signin/")
def signin(auth_data: SignInModel):
    """
    Авторизация клиента в системе
    В след версии API будет удалено,
    по скольку авторизация будет происходить при каждом запросе (JWT)

    """
    db = DBConnection(DB_PATH)
    client = db.get_client_by_login(auth_data.login)
    if not client:
        return {"success": False, "detail": "client not found"}

    if client["password"] != auth_data.password:
        return {"success": False, "detail": "Incorrect password"}
    db.update_client_telegram_id(client_id=client['id'], new_id=auth_data.telegram_id)
    return {"success": True, "detail": "Session has been updated"}
