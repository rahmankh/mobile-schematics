from django.db import models

from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.db import models
from django.utils import timezone


class CustomUserManager(BaseUserManager):
    """
    Manager for custom user model where phone_number is the unique identifier
    for authentication instead of usernames.
    """
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

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(phone_number, password, **extra_fields)


class CustomUser(AbstractBaseUser, PermissionsMixin):
    """
    Custom User model for mobile repair technicians and administrators.
    """
    class RoleChoices(models.TextChoices):
        TECHNICIAN = 'technician', 'Technician'
        ADMIN = 'admin', 'Admin'

    phone_number = models.CharField(
        max_length=15,
        unique=True,
        db_index=True,
        help_text="Unique phone number used for login and notifications."
    )
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    repair_shop_name = models.CharField(
        max_length=200, 
        blank=True, 
        help_text="Name of the mobile repair shop or center."
    )
    role = models.CharField(
        max_length=20, 
        choices=RoleChoices.choices, 
        default=RoleChoices.TECHNICIAN
    )
    
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    objects = CustomUserManager()

    USERNAME_FIELD = 'phone_number'
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = 'User'
        verbose_name_plural = 'Users'

    def __str__(self) -> str:
        return f"{self.phone_number} ({self.get_full_name() or 'No Name'})"

    def get_full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()
