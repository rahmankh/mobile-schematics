"""
Custom user for mobile-repair technicians.

Login identifier is `phone_number` (Iranian 09xxxxxxxxx), not email/username.
`role` is a product-level flag; staff access still uses `is_staff` / `is_superuser`.
"""

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class CustomUserManager(BaseUserManager):
    """Manager that creates technicians and superusers keyed by phone number."""

    def create_user(self, phone_number: str, password: str = None, **extra_fields):
        if not phone_number:
            raise ValueError('The Phone Number must be set')
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
        extra_fields.setdefault('role', CustomUser.RoleChoices.ADMIN)
        return self.create_user(phone_number, password, **extra_fields)


class CustomUser(AbstractBaseUser, PermissionsMixin):
    """Technician (default) or admin account. USERNAME_FIELD is phone_number."""

    class RoleChoices(models.TextChoices):
        TECHNICIAN = 'technician', _('Technician')
        ADMIN = 'admin', _('Admin')

    phone_number = models.CharField(
        _('Phone Number'),
        max_length=15,
        unique=True,
        db_index=True,
    )
    first_name = models.CharField(_('First Name'), max_length=150, blank=True)
    last_name = models.CharField(_('Last Name'), max_length=150, blank=True)
    repair_shop_name = models.CharField(
        _('Repair Shop Name'),
        max_length=200,
        blank=True,
    )
    role = models.CharField(
        _('Role'),
        max_length=20,
        choices=RoleChoices.choices,
        default=RoleChoices.TECHNICIAN,
        db_index=True,
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
        return f'{self.phone_number} ({self.get_full_name() or "No Name"})'

    def get_full_name(self) -> str:
        return f'{self.first_name} {self.last_name}'.strip()

    @property
    def is_guest(self) -> bool:
        """True when checkout created the row and no login password has been set."""
        return not self.has_usable_password()


class PasswordResetChallenge(models.Model):
    """
    One hashed, time-limited OTP for a password reset.

    The plaintext code is delivered once (SMS later; console while DEBUG) and
    never stored. Guests cannot receive a challenge — reset must not turn an
    unusable-password checkout row into a takeover.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='password_reset_challenges',
    )
    phone_number = models.CharField(max_length=15, db_index=True)
    otp_hash = models.CharField(max_length=64)
    expires_at = models.DateTimeField(db_index=True)
    attempt_count = models.PositiveSmallIntegerField(default=0)
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-created_at',)
        indexes = [
            models.Index(fields=('phone_number', 'used_at', 'expires_at')),
        ]
        verbose_name = _('Password reset challenge')
        verbose_name_plural = _('Password reset challenges')

    def __str__(self) -> str:
        state = 'used' if self.used_at else 'open'
        return f'{self.phone_number} ({state})'
