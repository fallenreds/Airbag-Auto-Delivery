import threading
import uvicorn
from asgi_correlation_id import CorrelationIdMiddleware
from fastapi import FastAPI, APIRouter
from fastapi.middleware.cors import CORSMiddleware
import logger
from UpdateOrdersTask import update_order_task

from api.auth import router as auth_router
from api.client_updates import router as client_updates_router
from api.clients import router as client_router
from api.discount import router as client_discount
from api.goods import router as goods_router
from api.orders import router as orders_router
from api.shoppingcart import router as shoppingcart_router
from api.templates import router as template_router
from api.visitors import router as visitors_router




app = FastAPI()

origins = [
    "http://localhost:3000",
    "https://stoshop.co.ua",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=r"https://.*\.ngrok-free\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(CorrelationIdMiddleware)
app.middleware("http")(logger.logging_middleware)

api_router = APIRouter(prefix='/api/v1')
api_router.include_router(auth_router)
api_router.include_router(client_updates_router)
api_router.include_router(client_router)
api_router.include_router(client_discount)
api_router.include_router(goods_router)
api_router.include_router(orders_router)
api_router.include_router(shoppingcart_router)
api_router.include_router(template_router)
api_router.include_router(visitors_router)


app.include_router(api_router)
logger.logger.info("backend_app_initialized")
upd_order_task = threading.Thread(target=update_order_task, daemon=True)
upd_order_task.start()
logger.logger.info("orders_background_thread_started", thread_name=upd_order_task.name)



if __name__ == "__main__":
    logger.logger.info("backend_uvicorn_starting", host="0.0.0.0", port=8000)
    uvicorn.run(app, host="0.0.0.0", port=8000)
