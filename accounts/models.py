from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class CustomUserManager(BaseUserManager):
    def create_user(self, phone_number: str, password: str = None, **extra_fields):
        if not phone_number:
            raise ValueError("The Phone Number must be set")
        user = self.model(phone_number=phone_number, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, phone_number: str, password: str = None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        return self.create_user(phone_number, password, **extra_fields)


class CustomUser(AbstractBaseUser, PermissionsMixin):
    class RoleChoices(models.TextChoices):
        TECHNICIAN = 'technician', _('Technician')
        ADMIN = 'admin', _('Admin')

    phone_number = models.CharField(
        _('Phone Number'),
        max_length=15,
        unique=True,
        db_index=True
    )
    first_name = models.CharField(_('First Name'), max_length=150, blank=True)
    last_name = models.CharField(_('Last Name'), max_length=150, blank=True)
    repair_shop_name = models.CharField(
        _('Repair Shop Name'),
        max_length=200, 
        blank=True
    )
    role = models.CharField(
        _('Role'),
        max_length=20, 
        choices=RoleChoices.choices, 
        default=RoleChoices.TECHNICIAN
    )
    
    is_active = models.BooleanField(_('Active'), default=True)
    is_staff = models.BooleanField(_('Staff Status'), default=False)
    date_joined = models.DateTimeField(_('Date Joined'), default=timezone.now)

    objects = CustomUserManager()

    USERNAME_FIELD = 'phone_number'
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = _('User')
        verbose_name_plural = _('Users')

    def __str__(self) -> str:
        return f"{self.phone_number} ({self.get_full_name() or 'No Name'})"

    def get_full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()