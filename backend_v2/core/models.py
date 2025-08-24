from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin,
)
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone  # keep import

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
    phone = models.CharField(max_length=20, blank=True, null=True)
    nova_post_address = models.TextField(blank=True, null=True)

    # Personal discount percent 0–100
    discount_percent = CustomPercentageField(default=0)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_guest = models.BooleanField(default=False)

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

    def save(self, *args, **kwargs):
        # Allow saving without email only for guest clients
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


class ClientUpdate(models.Model):
    id = models.BigAutoField(primary_key=True)
    type = models.CharField(max_length=32)
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="updates")
    # Use default for existing rows and auto-fill new ones
    created_at = models.DateTimeField(default=timezone.now, editable=False)


# ===== Catalog =====


class GoodCategory(models.Model):
    id = models.BigAutoField(primary_key=True)
    id_remonline = models.BigIntegerField()
    title = models.CharField(max_length=255)
    parent_id = models.BigIntegerField(null=True, blank=True)


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


class Order(models.Model):
    id = models.BigAutoField(primary_key=True)
    remonline_order_id = models.BigIntegerField(blank=True, null=True, db_index=True)

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
    is_paid = models.BooleanField(default=False)
    ttn = models.TextField(blank=True, null=True)
    is_completed = models.BooleanField(default=False)

    # Order aggregates in minor units
    discount_percent = CustomPercentageField(null=True, blank=True)
    subtotal_minor = models.BigIntegerField(default=0)  # before discounts/taxes
    discount_total_minor = models.BigIntegerField(default=0)  # total discount
    grand_total_minor = models.BigIntegerField(default=0)  # payable total

    description = models.TextField(blank=True, null=True)

    remember_count = models.IntegerField(default=0)
    branch_remember_count = models.IntegerField(default=0)
    in_branch_datetime = models.DateTimeField(blank=True, null=True)

    date = models.DateTimeField(auto_now_add=True)

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


class OrderUpdate(models.Model):
    id = models.BigAutoField(primary_key=True)
    type = models.CharField(max_length=32)
    details = models.TextField(blank=True, null=True)
    # keep both raw textual order id and FK link if available
    order = models.CharField(max_length=255, blank=True, null=True)
    order_ref = models.ForeignKey(
        "Order",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_updates",
    )
    created_at = models.DateTimeField(auto_now_add=True)


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


class BotVisitor(models.Model):
    id = models.BigAutoField(primary_key=True)
    telegram_id = models.BigIntegerField(unique=True)

    def __str__(self):
        return str(self.telegram_id)
