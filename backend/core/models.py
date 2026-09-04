import secrets

from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin,
)
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone  # keep import

from core.text_utils import transliterate_slug

# ===== Common =====


class CustomPercentageField(models.DecimalField):
    """0–100 with two decimal places."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("max_digits", 5)
        kwargs.setdefault("decimal_places", 2)
        super().__init__(*args, **kwargs)
        self.validators.append(MinValueValidator(0))
        self.validators.append(MaxValueValidator(100))


# ===== User =====


class ClientManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email must be set")
        extra_fields.setdefault("is_active", True)
        user = self.model(email=self.normalize_email(email), **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_guest(self, **extra_fields):
        """
        Create a guest client with no email and no password.
        Guest clients can be created with just an ID - no other fields required.
        Guest clients can be converted to regular clients later.
        """
        # Set minimal defaults but allow them to be null/blank
        extra_fields.setdefault("is_guest", True)
        extra_fields.setdefault("is_active", True)

        # Create with just the required fields
        # Skip email validation for guest users
        user = self.model(**extra_fields)
        user._skip_email_validation = True  # Add a flag to skip validation
        user.set_unusable_password()  # Set an unusable password
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self.create_user(email, password, **extra_fields)


class Client(AbstractBaseUser, PermissionsMixin):
    id = models.BigAutoField(primary_key=True)
    id_remonline = models.BigIntegerField(null=True, blank=True)
    telegram_id = models.BigIntegerField(null=True, blank=True, db_index=True)

    name = models.CharField(max_length=255, null=True, blank=True)
    last_name = models.CharField(max_length=255, null=True, blank=True)
    login = models.CharField(max_length=128, unique=True, null=True, blank=True)

    email = models.EmailField(unique=True, max_length=100, null=True, blank=True)
    phone = models.CharField(max_length=20, blank=True, null=True, unique=True)
    nova_post_address = models.TextField(blank=True, null=True)

    api_key = models.CharField(max_length=255, unique=True, null=True, blank=True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_guest = models.BooleanField(default=False)
    # Подтверждение почты при регистрации. Новые аккаунты создаются
    # неподтверждёнными и не могут войти, пока не пройдут по ссылке из письма.
    # Существующие на момент миграции аккаунты помечены подтверждёнными —
    # иначе действующие клиенты разом потеряли бы доступ.
    email_confirmed = models.BooleanField(default=False)

    groups = models.ManyToManyField(
        "auth.Group",
        related_name="client_set",
        blank=True,
        help_text="The groups this user belongs to.",
        verbose_name="groups",
    )
    user_permissions = models.ManyToManyField(
        "auth.Permission",
        related_name="client_set",
        blank=True,
        help_text="Specific permissions for this user.",
        verbose_name="user permissions",
    )

    objects = ClientManager()
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    def generate_api_key(self):
        self.api_key = secrets.token_urlsafe(32)

    def save(self, *args, **kwargs):
        # Allow saving without email only for guest clients
        if not self.pk:
            self.generate_api_key()

        if getattr(self, "_skip_email_validation", False) or self.is_guest:
            # Skip the email validation for guest clients
            super(AbstractBaseUser, self).save(*args, **kwargs)
        else:
            # Normal save with validation for regular clients
            super().save(*args, **kwargs)

    def __str__(self):
        name = self.name or ""
        last_name = self.last_name or ""
        email_part = f" ({self.email})" if self.email else ""

        if name or last_name:
            return f"{name} {last_name}{email_part}"
        return f"Guest{email_part}" if self.is_guest else "Client"


class ClientEventType:
    """
    Коды событий клиента.

    Тот же контракт, что и у `OrderEventType`: строка из этого списка уезжает
    в очередь, бот разбирает её по точному совпадению. Менять значения нельзя
    — только добавлять, и одновременно с веткой в `bot/updates.py`.
    """

    CREATED = "CREATED"

    CHOICES = [
        (CREATED, "Created"),
    ]


class ClientEvent(models.Model):
    id = models.BigAutoField(primary_key=True)
    type = models.CharField(max_length=32)
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="events")
    # Use default for existing rows and auto-fill new ones
    created_at = models.DateTimeField(default=timezone.now, editable=False)


# ===== Catalog =====


class GoodCategory(models.Model):
    id = models.BigAutoField(primary_key=True)
    id_remonline = models.BigIntegerField()
    title = models.CharField(max_length=255)
    parent_id = models.BigIntegerField(null=True, blank=True)

    image = models.ImageField(
        upload_to="categories/",
        null=True,
        blank=True
    )

    # ===== SEO =====
    # Transliterated slug auto-derived from title (mirrors frontend slugify).
    # Not unique: titles may repeat; routing relies on the trailing id.
    slug = models.SlugField(max_length=280, blank=True, db_index=True)
    meta_title = models.CharField(max_length=255, blank=True, null=True)
    meta_description = models.TextField(blank=True, null=True)


    def save(self, *args, **kwargs):
        if not self.slug and self.title:
            self.slug = transliterate_slug(self.title)
        super().save(*args, **kwargs)


class Good(models.Model):
    id = models.BigAutoField(primary_key=True)
    id_remonline = models.BigIntegerField()
    title = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    images = models.JSONField(null=True, blank=True)
    together_buy = models.JSONField(
        null=True,
        blank=True,
        default=list,
        help_text="Optional list of related Good IDs (bigint) often bought together",
    )

    # List price in minor units
    price_minor = models.BigIntegerField(default=0)  # >= 0
    currency = models.CharField(max_length=3, default="UAH")  # ISO-4217

    residue = models.IntegerField(default=0)
    code = models.CharField(max_length=32, null=True, blank=True)
    category = models.ForeignKey(
        "GoodCategory",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="goods",
    )

    # ===== SEO =====
    # Transliterated slug auto-derived from title (mirrors frontend slugify).
    # Not unique: titles may repeat; routing relies on the trailing id.
    slug = models.SlugField(max_length=280, blank=True, db_index=True)
    meta_title = models.CharField(max_length=255, blank=True, null=True)
    meta_description = models.TextField(blank=True, null=True)

    # Название в нижнем регистре — по нему идёт поиск.
    #
    # SQLite сравнивает без учёта регистра только ASCII: `title__icontains="пп"`
    # не находил «ПП сиденье», хотя `original` и `ORIGINAL` работали одинаково.
    # Привести к нижнему регистру средствами БД нельзя — её `LOWER()` страдает
    # тем же, — поэтому храним готовую копию и ищем по ней.
    search_title = models.CharField(max_length=255, blank=True, db_index=True)

    def save(self, *args, **kwargs):
        if not self.slug and self.title:
            self.slug = transliterate_slug(self.title)
        self.search_title = (self.title or "").lower()
        super().save(*args, **kwargs)

    @staticmethod
    def convert_minore_to_major(price_minor):
        return price_minor / 100

    @staticmethod
    def parse_ids_string(value: str):
        """Convert a string like "1, 2,3" into a list of ints [1,2,3], ignoring spaces.

        Non-integer tokens are skipped. Empty or None returns [].
        """
        if not value:
            return []
        # Remove all spaces and split by comma
        compact = value.replace(" ", "")
        if not compact:
            return []
        result = []
        for token in compact.split(","):
            if not token:
                continue
            try:
                result.append(int(token))
            except ValueError:
                # Skip non-numeric tokens silently
                continue
        return result


# ===== Discounts (history-based etc.) =====


class Discount(models.Model):
    id = models.BigAutoField(primary_key=True)
    percentage = CustomPercentageField()
    month_payment = models.BigIntegerField(
        help_text="Total payments for the month in minor units"
    )


# ===== Orders =====


class CancelReason:
    """Причины отмены. Клиентские + админские (последние два)."""

    CHANGED_MIND = "changed_mind"
    FOUND_CHEAPER = "found_cheaper"
    WRONG_ITEMS = "wrong_items"
    DELIVERY_TOO_LONG = "delivery_too_long"
    DUPLICATE = "duplicate"
    PAYMENT_FAILED = "payment_failed"
    OTHER = "other"
    NO_CONTACT = "no_contact"
    OUT_OF_STOCK = "out_of_stock"
    REMOVED_IN_REMONLINE = "removed_in_remonline"
    MERGED = "merged"

    CLIENT_CHOICES = [
        CHANGED_MIND,
        FOUND_CHEAPER,
        WRONG_ITEMS,
        DELIVERY_TOO_LONG,
        DUPLICATE,
        PAYMENT_FAILED,
        OTHER,
    ]

    CHOICES = [
        (CHANGED_MIND, "Changed mind"),
        (FOUND_CHEAPER, "Found cheaper"),
        (WRONG_ITEMS, "Wrong items"),
        (DELIVERY_TOO_LONG, "Delivery too long"),
        (DUPLICATE, "Duplicate order"),
        (PAYMENT_FAILED, "Payment failed"),
        (OTHER, "Other"),
        (NO_CONTACT, "No contact with client"),
        (OUT_OF_STOCK, "Out of stock"),
        (REMOVED_IN_REMONLINE, "Removed in Remonline"),
        (MERGED, "Merged into another order"),
    ]


# Бонусные начисления оформлены служебным заказом (см. ClientViewSet.add_bonus):
# состава у него нет, он существует только чтобы попасть в сумму месяца, из
# которой DiscountService считает скидку. По этому маркеру такие заказы
# прячутся от клиента.
BONUS_ORDER_MARKER = "BONUS"


class Order(models.Model):
    class RemonlineSyncStatus:
        PENDING = "PENDING"
        SYNCED = "SYNCED"
        # Запись в CRM сорвалась: сеть, 401, 502. Отдельно от PENDING, потому
        # что по одному «ещё не синхронизирован» нельзя было отличить заказ,
        # честно ждущий оплаты, от заказа, который в CRM уже не попадёт
        # никогда. Такие заказы дотягивает крон и показывает фильтр в админке.
        FAILED = "FAILED"

        CHOICES = [
            (PENDING, "Pending"),
            (SYNCED, "Synced"),
            (FAILED, "Failed"),
        ]

    class CancelState:
        NONE = ""
        REQUESTED = "requested"
        CANCELED = "canceled"
        REJECTED = "rejected"

        CHOICES = [
            (NONE, "Not canceled"),
            (REQUESTED, "Cancellation requested"),
            (CANCELED, "Canceled"),
            (REJECTED, "Cancellation rejected"),
        ]

    class RefundState:
        NONE = ""
        PENDING = "pending"
        DONE = "done"
        MANUAL = "manual"
        FAILED = "failed"

        CHOICES = [
            (NONE, "No refund"),
            (PENDING, "Refund in progress"),
            (DONE, "Refunded"),
            (MANUAL, "Refunded manually"),
            (FAILED, "Refund failed"),
        ]

    id = models.BigAutoField(primary_key=True)
    remonline_order_id = models.BigIntegerField(blank=True, null=True, db_index=True)
    remonline_sync_status = models.CharField(
        max_length=16,
        choices=RemonlineSyncStatus.CHOICES,
        default=RemonlineSyncStatus.PENDING,
    )
    # Сколько раз подряд не удалось записать заказ в CRM. Нужен, чтобы
    # перестать долбиться в недоступный сервис и один раз сказать админу, что
    # заказ туда так и не уехал.
    remonline_sync_attempts = models.PositiveSmallIntegerField(default=0)

    client = models.ForeignKey(
        "Client", on_delete=models.SET_NULL, null=True, related_name="orders"
    )
    telegram_id = models.BigIntegerField(null=True, blank=True, db_index=True)

    # Contact snapshot at order time
    name = models.CharField(max_length=255)
    last_name = models.CharField(max_length=255)
    phone = models.CharField(max_length=20)
    nova_post_address = models.TextField()

    prepayment = models.BooleanField(default=False)
    bank_transfer = models.BooleanField(default=False)
    payment_document = models.FileField(upload_to='payment_docs/', null=True, blank=True)
    is_paid = models.BooleanField(default=False)
    # Черновик — заказ с оплатой картой, который ещё не оплачен. Он не виден
    # нигде: ни в кабинете клиента, ни в списках бота, ни при выборе заказа для
    # объединения, ни в CRM. Обычным заказом становится по вебхуку об успешной
    # оплате.
    #
    # Отдельное поле, а не вычисление «предоплата и не оплачен»: заказ,
    # оплаченный и потом отменённый, под такое вычисление снова попал бы в
    # черновики.
    is_draft = models.BooleanField(default=False, db_index=True)
    ttn = models.TextField(blank=True, null=True)
    is_completed = models.BooleanField(default=False)

    # Order aggregates in minor units
    discount_percent = CustomPercentageField(null=True, blank=True)
    subtotal_minor = models.BigIntegerField(default=0)  # before discounts/taxes
    discount_total_minor = models.BigIntegerField(default=0)  # total discount
    grand_total_minor = models.BigIntegerField(default=0)  # payable total

    # Отмена заказа. is_paid при возврате не сбрасывается — факт оплаты был,
    # состояние возврата живёт отдельно в refund_state.
    cancel_state = models.CharField(
        max_length=16,
        choices=CancelState.CHOICES,
        default=CancelState.NONE,
        blank=True,
        db_index=True,
    )
    cancel_reason = models.CharField(
        max_length=32, choices=CancelReason.CHOICES, null=True, blank=True
    )
    cancel_comment = models.TextField(blank=True, null=True)
    cancel_requested_at = models.DateTimeField(null=True, blank=True)
    canceled_at = models.DateTimeField(null=True, blank=True)
    canceled_by = models.ForeignKey(
        "Client",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="canceled_orders",
    )
    refund_state = models.CharField(
        max_length=16,
        choices=RefundState.CHOICES,
        default=RefundState.NONE,
        blank=True,
    )

    description = models.TextField(blank=True, null=True)

    remember_count = models.IntegerField(default=0)
    branch_remember_count = models.IntegerField(default=0)
    in_branch_datetime = models.DateTimeField(blank=True, null=True)

    date = models.DateTimeField(auto_now_add=True)

    @property
    def is_prepaid_flow(self) -> bool:
        """
        Клиент платит до отгрузки — картой онлайн или по реквизитам.

        Именованное свойство, а не проверка флагов по месту: условие нужно в
        шести местах (отправка в CRM, доступность онлайн-счёта, подписи типа
        оплаты, кнопки в боте), и разъехавшись, оно разъедется незаметно.
        """
        return bool(self.prepayment or self.bank_transfer)

    @property
    def is_online_payment(self) -> bool:
        """Оплата картой: платит до отгрузки, но не по реквизитам."""
        return bool(self.prepayment and not self.bank_transfer)

    @property
    def payment_kind(self) -> str:
        """
        Способ оплаты одним значением — для сравнения двух заказов между собой.

        Объединять разрешено только однотипные заказы, и «однотипность» должна
        считаться в одном месте.
        """
        if self.bank_transfer:
            return "bank_transfer"
        if self.prepayment:
            return "online"
        return "postpaid"

    class Meta:
        indexes = [
            models.Index(fields=["date"]),
            models.Index(fields=["client", "date"]),
        ]


class OrderItem(models.Model):
    order = models.ForeignKey("Order", on_delete=models.CASCADE, related_name="items")
    good = models.ForeignKey("Good", on_delete=models.SET_NULL, null=True, blank=True)

    # Product snapshot at purchase time
    good_external_id = models.BigIntegerField(null=False)
    id_remonline = models.BigIntegerField()  # external Remonline ID
    title = models.CharField(max_length=255)
    code = models.CharField(max_length=32, blank=True, null=True)
    category_id = models.BigIntegerField(null=True, blank=True)

    quantity = models.PositiveIntegerField()

    currency = models.CharField(max_length=3, default="UAH")

    # Pricing in minor units
    original_price_minor = models.BigIntegerField(default=0)  # per-unit before discount
    discount_percent = CustomPercentageField(null=True, blank=True)  # optional
    discount_minor = models.BigIntegerField(default=0)  # row-level discount
    unit_price_minor = models.BigIntegerField(default=0)  # per-unit after discount
    line_subtotal_minor = models.BigIntegerField(
        default=0
    )  # unit_price_minor * quantity
    line_total_minor = models.BigIntegerField(default=0)

    class Meta:
        indexes = [
            models.Index(fields=["order"]),
        ]


class OrderEventType:
    MERGED = "MERGED"
    CREATED_ADMIN_MESSAGE = "CREATED_ADMIN_MESSAGE"
    CREATED_CLIENT_MESSAGE = "CREATED_CLIENT_MESSAGE"
    FINISHED = "FINISHED"
    TTN_UPDATED = "TTN_UPDATED"
    IN_BRANCH = "IN_BRANCH"
    PAYMENT_CONFIRMED = "PAYMENT_CONFIRMED"
    REMONLINE_CREATED = "REMONLINE_CREATED"
    PAYMENT_TYPE_CHANGED = "PAYMENT_TYPE_CHANGED"
    PAYMENT_DOC_UPLOADED = "PAYMENT_DOC_UPLOADED"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCELED = "CANCELED"
    CANCEL_REJECTED = "CANCEL_REJECTED"
    REFUNDED = "REFUNDED"
    REMONLINE_SYNC_FAILED = "REMONLINE_SYNC_FAILED"

    CHOICES = [
        (MERGED, "Merged"),
        (CREATED_ADMIN_MESSAGE, "Created Admin Message"),
        (CREATED_CLIENT_MESSAGE, "Created Client Message"),
        (FINISHED, "Finished"),
        (TTN_UPDATED, "TTN Updated"),
        (IN_BRANCH, "In Branch"),
        (PAYMENT_CONFIRMED, "Payment Confirmed"),
        (REMONLINE_CREATED, "Remonline Created"),
        (PAYMENT_TYPE_CHANGED, "Payment Type Changed"),
        (PAYMENT_DOC_UPLOADED, "Payment Document Uploaded"),
        (CANCEL_REQUESTED, "Cancellation Requested"),
        (CANCELED, "Canceled"),
        (CANCEL_REJECTED, "Cancellation Rejected"),
        (REFUNDED, "Refunded"),
        (REMONLINE_SYNC_FAILED, "Remonline Sync Failed"),
    ]


class OrderEvent(models.Model):
    id = models.BigAutoField(primary_key=True)
    type = models.CharField(max_length=32, choices=OrderEventType.CHOICES)
    details = models.TextField(blank=True, null=True)
    order = models.ForeignKey(
        "Order",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_events",
    )
    created_at = models.DateTimeField(auto_now_add=True)


class BankDetails(models.Model):
    """Bank details for 'pay by bank transfer' payment method. Single active record."""
    full_name = models.CharField(max_length=255, blank=True, default="")
    card_number = models.CharField(max_length=64, blank=True, default="")
    account_number = models.CharField(max_length=64, blank=True, default="")
    edrpou = models.CharField(max_length=32, blank=True, default="")
    payment_purpose = models.CharField(max_length=255, blank=True, default="")
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Bank Details"
        verbose_name_plural = "Bank Details"

    def __str__(self):
        return f"{self.full_name} — {self.card_number}"


# ===== Cart =====


class Cart(models.Model):
    client = models.OneToOneField(
        "Client", on_delete=models.CASCADE, related_name="cart", null=True, blank=True
    )
    telegram_id = models.BigIntegerField(null=True, blank=True, unique=True)
    currency = models.CharField(max_length=3, default="UAH")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class CartItem(models.Model):
    cart = models.ForeignKey("Cart", on_delete=models.CASCADE, related_name="items")
    good = models.ForeignKey("Good", on_delete=models.CASCADE)
    count = models.PositiveIntegerField()

    class Meta:
        unique_together = ("cart", "good")


# ===== Templates and bot visitors =====


class Template(models.Model):
    id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=255)
    text = models.TextField()


class AccountClaimCode(models.Model):
    """
    Персональная ссылка, которой старый клиент забирает свой аккаунт.

    Клиенты, приехавшие из старой системы, попадают в базу без почты — там её
    просто не спрашивали, и взять её неоткуда (проверены и заказы, и RemOnline).
    А вход на сайт устроен по почте. Получается тупик: войти нечем, сбросить
    пароль нечем, а регистрация со своим телефоном упирается в «номер занят» —
    занят его же собственной записью.

    Код разрывает этот круг: бот присылает клиенту ссылку с кодом, клиент
    задаёт почту и пароль, и они попадают в ту же запись — вместе с историей
    заказов, накопленной скидкой и связью с RemOnline.

    Кода хватает как доказательства личности: он приходит в личный чат
    Telegram, привязанный к записи ещё в старой системе.
    """

    CODE_BYTES = 24

    id = models.BigAutoField(primary_key=True)
    client = models.OneToOneField(
        "Client", on_delete=models.CASCADE, related_name="claim_code"
    )
    code = models.CharField(max_length=64, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    # Проставляется рассылкой: команда идемпотентна и не шлёт повторно.
    sent_at = models.DateTimeField(null=True, blank=True)

    @staticmethod
    def generate_code():
        return secrets.token_urlsafe(AccountClaimCode.CODE_BYTES)

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = self.generate_code()
        super().save(*args, **kwargs)

    @property
    def is_spent(self):
        """
        Код погашен, когда клиент подтвердил почту.

        Специально не гасим его в момент ввода: человек, опечатавшийся в
        адресе, иначе остался бы заперт навсегда — письмо ушло в никуда, а
        ссылка уже сгорела. Пока почта не подтверждена, по ссылке можно
        вернуться и ввести другую.
        """
        return bool(self.client.email and self.client.email_confirmed)

    def __str__(self):
        return f"claim for {self.client_id}"


class BotVisitor(models.Model):
    id = models.BigAutoField(primary_key=True)
    telegram_id = models.BigIntegerField(unique=True)

    def __str__(self):
        return str(self.telegram_id)
