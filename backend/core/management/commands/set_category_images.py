import os
from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand

from core.models import GoodCategory

# Папка, где лежат картинки категорий.
# Если у тебя другая, просто поправь путь.
CATEGORY_LOGO_DIR = Path(settings.BASE_DIR) / "staticfiles" / "category-logo"


CATEGORIES_DATA = [
    {"id": 753903, "image": "acura.jpg"},
    {"id": 753902, "image": "audi.jpg"},
    {"id": 753904, "image": "bmw.jpg"},
    {"id": 753906, "image": "buick.jpg"},
    {"id": 1121716, "image": "cadillac.jpg"},
    {"id": 753907, "image": "chevrolet.jpg"},
    {"id": 753905, "image": "dodge.jpg"},
    {"id": 1140060, "image": "fiat.jpg"},
    {"id": 753908, "image": "ford.jpg"},
    {"id": 1121717, "image": "gmc.jpg"},
    {"id": 753909, "image": "honda.jpg"},
    {"id": 753900, "image": "hundai.jpg"},
    {"id": 753922, "image": "infinity.jpg"},
    {"id": 1140061, "image": "jagar.jpg"},
    {"id": 753896, "image": "jeep.jpg"},
    {"id": 1121713, "image": "kia.jpg"},
    {"id": 753901, "image": "lexus.jpg"},
    {"id": 1077872, "image": "land_rover.jpg"},
    {"id": 753910, "image": "lincoln.jpg"},
    {"id": 1140062, "image": "mini_cooper.jpg"},
    {"id": 753912, "image": "mazda.jpg"},
    {"id": 1121715, "image": "mercedes.jpg"},
    {"id": 753911, "image": "mitsubishi.jpg"},
    {"id": 1105320, "image": "mustang.jpg"},
    {"id": 753913, "image": "nissan.jpg"},
    {"id": 875421, "image": "porsche.jpg"},
    {"id": 753914, "image": "subaru.jpg"},
    {"id": 753915, "image": "toyota.jpg"},
    {"id": 753921, "image": "tesla.jpg"},
    {"id": 753916, "image": "vw.jpg"},
    {"id": 1140059, "image": "volvo.jpg"},
    {"id": 753898, "image": "pp-nogi-sedenie.jpg"},
    {"id": 753917, "image": "connektory.jpg"},
    {"id": 753918, "image": "kreplenia.jpg"},
    {"id": 753919, "image": "obmanki-rezistory.jpg"},
    {"id": 753897, "image": "parashuty-meshki.jpg"},
    {"id": 753899, "image": "capchasti-dlya-remnei.jpg"},
    {"id": 753920, "image": "pp-v-remni.jpg"},
    {"id": 753924, "image": "pp-v-shtory.jpg"},
    {"id": 754102, "image": None},  # ПП в руль
    {"id": 753926, "image": "pp-v-rul-1-zapal.jpg"},
    {"id": 753925, "image": "pp-v-rul-2-zapal.jpg"},
    {"id": 753928, "image": "pp-torpedo-1-zapal.jpg"},
    {"id": 753928, "image": "pp-torpedo-1-zapal.jpg"},
    {"id": 753927, "image": "pp-torpedo-2-zapal.jpg"},
    {"id": 754099, "image": None},
    {"id": 754100, "image": None},
    {"id": 754101, "image": None},
]


class Command(BaseCommand):
    help = "Одноразово проставляет изображения категориям из staticfiles/categorylogo по id."

    def handle(self, *args, **options):
        if not CATEGORY_LOGO_DIR.exists():
            self.stderr.write(
                self.style.ERROR(f"Папка с картинками не найдена: {CATEGORY_LOGO_DIR}")
            )
            return

        # Индекс по идентификатору (id из JSON = внешний идентификатор)
        json_by_id = {int(item["id"]): item for item in CATEGORIES_DATA}
        updated = 0
        skipped_no_match = 0
        skipped_no_file = 0
        already_set = 0

        for category in GoodCategory.objects.all():
            # Сначала переводим модель в dict, потом работаем с ключами
            cat_dict = {
                "id": category.id,
            }

            ident = cat_dict.get("id")
            matched_item = None

            if ident is not None and int(ident) in json_by_id:
                matched_item = json_by_id[int(ident)]

            if not matched_item:
                skipped_no_match += 1
                self.stdout.write(
                    self.style.WARNING(
                        f"Нет совпадения по id для категории {category.id} ({category.title})"
                    )
                )
                continue

            image_name = matched_item.get("image")
            if not image_name:
                skipped_no_file += 1
                self.stdout.write(
                    self.style.WARNING(
                        f"Для категории {category.id} ({category.title}) в JSON нет имени файла изображения"
                    )
                )
                continue

            image_path = CATEGORY_LOGO_DIR / image_name

            if not image_path.exists():
                skipped_no_file += 1
                self.stdout.write(
                    self.style.WARNING(
                        f"Файл изображения не найден: {image_path} для категории {category.id} ({category.title})"
                    )
                )
                continue

            if category.image:
                already_set += 1
                self.stdout.write(
                    self.style.NOTICE(
                        f"У категории {category.id} ({category.title}) уже есть изображение, пропускаю"
                    )
                )
                continue

            # Сохраняем файл в ImageField (upload_to="categories/")
            with open(image_path, "rb") as f:
                filename = f"{category.id}_{os.path.basename(image_name)}"
                category.image.save(filename, File(f), save=False)

            category.save(update_fields=["image"])
            updated += 1
            self.stdout.write(
                self.style.SUCCESS(
                    f"Установлено изображение {image_name} для категории {category.id} ({category.title})"
                )
            )

        self.stdout.write(self.style.SUCCESS("Готово."))
        self.stdout.write(
            self.style.SUCCESS(
                f"Обновлено: {updated}, уже были картинки: {already_set}, "
                f"нет совпадения: {skipped_no_match}, нет файла/имени файла: {skipped_no_file}"
            )
        )
