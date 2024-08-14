from enum import Enum

class AdminLabels(Enum):
    notAdmin: str = "Вы не являетесь администратором!"
    enter_notifications: str = "Шановний адміністратор. Ви зайшли до меню керування, <b>будьте обачні перш ніж обирати</b>"