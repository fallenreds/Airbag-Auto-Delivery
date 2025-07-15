from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
class ClientManager(BaseUserManager):
    def create_user(self, login, password=None, **extra_fields):
        if not login:
            raise ValueError('Login must be set')
        user = self.model(login=login, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user
    def create_superuser(self, login, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')
        return self.create_user(login, password, **extra_fields)


class Client(AbstractBaseUser, PermissionsMixin):
    id = models.BigAutoField(primary_key=True)
    id_remonline = models.BigIntegerField()
    telegram_id = models.BigIntegerField()
    name = models.CharField(max_length=255)
    last_name = models.CharField(max_length=255)
    login = models.CharField(max_length=128, unique=True)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)
    groups = models.ManyToManyField(
        'auth.Group',
        related_name='client_set',
        blank=True,
        help_text='The groups this user belongs to.',
        verbose_name='groups',
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        related_name='client_set',
        blank=True,
        help_text='Specific permissions for this user.',
        verbose_name='user permissions',
    )
    objects = ClientManager()
    USERNAME_FIELD = 'login'
    REQUIRED_FIELDS = []
    def __str__(self):
        return f"{self.name} {self.last_name} ({self.login})"
class ClientUpdate(models.Model):
    id = models.BigAutoField(primary_key=True)
    type = models.CharField(max_length=32)
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='updates')
class Discount(models.Model):
    id = models.BigAutoField(primary_key=True)
    procent = models.IntegerField()
    month_payment = models.IntegerField()
class OrderUpdate(models.Model):
    id = models.BigAutoField(primary_key=True)
    type = models.CharField(max_length=32)
    details = models.TextField(blank=True, null=True)
    order = models.CharField(max_length=255, blank=True, null=True)
    order_ref = models.ForeignKey('Order', on_delete=models.SET_NULL, null=True, blank=True, related_name='order_updates')

class Order(models.Model):
    id = models.BigAutoField(primary_key=True)
    remonline_order_id = models.BigIntegerField(blank=True, null=True)
    client = models.ForeignKey('Client', on_delete=models.SET_NULL, null=True, related_name='orders')
    telegram_id = models.BigIntegerField()
    name = models.CharField(max_length=255)
    last_name = models.CharField(max_length=255)
    prepayment = models.BooleanField(default=False)
    phone = models.CharField(max_length=20)
    nova_post_address = models.TextField()
    description = models.TextField(blank=True, null=True)
    is_paid = models.BooleanField(default=False)
    ttn = models.TextField(blank=True, null=True)
    is_completed = models.BooleanField(default=False)
    date = models.DateTimeField(auto_now_add=True)
    remember_count = models.IntegerField(default=0)
    branch_remember_count = models.IntegerField(default=0)
    in_branch_datetime = models.DateTimeField(blank=True, null=True)
    # Теперь связь с товарами через OrderItem

class OrderItem(models.Model):
    order = models.ForeignKey('Order', on_delete=models.CASCADE, related_name='items')
    good = models.ForeignKey('Good', on_delete=models.SET_NULL, null=True)
    count = models.PositiveIntegerField()
    price = models.IntegerField()  # Цена на момент заказа


class Cart(models.Model):
    client = models.OneToOneField('Client', on_delete=models.CASCADE, related_name='cart', null=True, blank=True)
    telegram_id = models.BigIntegerField(null=True, blank=True, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class CartItem(models.Model):
    cart = models.ForeignKey('Cart', on_delete=models.CASCADE, related_name='items')
    good = models.ForeignKey('Good', on_delete=models.CASCADE)
    count = models.PositiveIntegerField()

    class Meta:
        unique_together = ('cart', 'good')

class Template(models.Model):
    id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=255)
    text = models.TextField()
    
class BotVisitor(models.Model):
    id = models.BigAutoField(primary_key=True)
    telegram_id = models.BigIntegerField(unique=True)
    def __str__(self):
        return str(self.telegram_id)

class Good(models.Model):
    id = models.BigAutoField(primary_key=True)
    id_remonline = models.BigIntegerField()
    title = models.CharField(max_length=255)
    description = models.TextField()
    images = models.JSONField()
    price = models.IntegerField()
    residue = models.IntegerField()
    code = models.IntegerField()
    category = models.ForeignKey('GoodCategory', on_delete=models.SET_NULL, null=True, blank=True, related_name='goods')
    
class GoodCategory(models.Model):
    id = models.BigAutoField(primary_key=True)
    id_remonline = models.BigIntegerField()
    title = models.CharField(max_length=255)
    parent_id = models.BigIntegerField(null=True, blank=True)
    
