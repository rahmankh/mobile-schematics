"""Session auth forms for the HTML catalog (phone number, not email)."""

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.exceptions import ValidationError as DRFValidationError

from accounts.password_reset import (
    GENERIC_CONFIRM_ERROR,
    InvalidResetError,
    confirm_password_reset,
    request_password_reset,
)
from accounts.phone import normalize_iranian_phone

User = get_user_model()


def _normalized_phone(value: str) -> str:
    try:
        return normalize_iranian_phone(value)
    except DRFValidationError as exc:
        detail = exc.detail
        message = detail[0] if isinstance(detail, list) else detail
        raise DjangoValidationError(str(message)) from exc


class PhoneAuthenticationForm(AuthenticationForm):
    """
    Django's AuthenticationForm still posts `username`, but the label and
    placeholder match CustomUser.USERNAME_FIELD (phone_number).
    """

    username = forms.CharField(
        label='شماره موبایل',
        widget=forms.TextInput(
            attrs={
                'autocomplete': 'username',
                'inputmode': 'tel',
                'dir': 'ltr',
                'placeholder': '0912xxxxxxx',
            }
        ),
    )
    password = forms.CharField(
        label='رمز عبور',
        widget=forms.PasswordInput(
            attrs={
                'autocomplete': 'current-password',
                'placeholder': '••••••••',
            }
        ),
    )

    def clean_username(self) -> str:
        return _normalized_phone(self.cleaned_data['username'])


class TechnicianRegisterForm(forms.Form):
    """HTML signup. Same rules as POST /api/v1/accounts/register/ (technician only)."""

    phone_number = forms.CharField(
        label='شماره موبایل',
        widget=forms.TextInput(
            attrs={
                'autocomplete': 'tel',
                'inputmode': 'tel',
                'dir': 'ltr',
                'placeholder': '0912xxxxxxx',
            }
        ),
    )
    first_name = forms.CharField(label='نام', max_length=150, required=False)
    last_name = forms.CharField(label='نام خانوادگی', max_length=150, required=False)
    repair_shop_name = forms.CharField(label='نام تعمیرگاه', max_length=200, required=False)
    password = forms.CharField(
        label='رمز عبور',
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password', 'placeholder': '••••••••'}),
    )
    password_confirm = forms.CharField(
        label='تکرار رمز عبور',
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password', 'placeholder': '••••••••'}),
    )

    def clean_phone_number(self) -> str:
        phone = _normalized_phone(self.cleaned_data['phone_number'])
        if User.objects.filter(phone_number=phone).exists():
            raise DjangoValidationError('کاربری با این شماره موبایل قبلاً ثبت‌نام کرده است.')
        return phone

    def clean_password(self) -> str:
        password = self.cleaned_data['password']
        validate_password(password)
        return password

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get('password')
        confirm = cleaned.get('password_confirm')
        if password and confirm and password != confirm:
            self.add_error('password_confirm', 'رمزهای عبور وارد شده یکسان نیستند.')
        return cleaned

    def save(self):
        data = self.cleaned_data
        return User.objects.create_user(
            phone_number=data['phone_number'],
            password=data['password'],
            first_name=data.get('first_name') or '',
            last_name=data.get('last_name') or '',
            repair_shop_name=data.get('repair_shop_name') or '',
            role=User.RoleChoices.TECHNICIAN,
            is_staff=False,
            is_superuser=False,
        )


class PasswordResetRequestForm(forms.Form):
    """HTML step 1: phone only. Same silent send as the API."""

    phone_number = forms.CharField(
        label='شماره موبایل',
        widget=forms.TextInput(
            attrs={
                'autocomplete': 'tel',
                'inputmode': 'tel',
                'dir': 'ltr',
                'placeholder': '0912xxxxxxx',
            }
        ),
    )

    def clean_phone_number(self) -> str:
        return _normalized_phone(self.cleaned_data['phone_number'])

    def send(self) -> None:
        request_password_reset(self.cleaned_data['phone_number'])


class PasswordResetConfirmForm(forms.Form):
    """HTML step 2: OTP + new password. Does not start a session."""

    phone_number = forms.CharField(
        label='شماره موبایل',
        widget=forms.TextInput(
            attrs={
                'autocomplete': 'tel',
                'inputmode': 'tel',
                'dir': 'ltr',
                'placeholder': '0912xxxxxxx',
            }
        ),
    )
    otp = forms.CharField(
        label='کد بازیابی',
        max_length=16,
        widget=forms.TextInput(
            attrs={
                'autocomplete': 'one-time-code',
                'inputmode': 'numeric',
                'dir': 'ltr',
                'placeholder': '------',
            }
        ),
    )
    password = forms.CharField(
        label='رمز عبور جدید',
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password', 'placeholder': '••••••••'}),
    )
    password_confirm = forms.CharField(
        label='تکرار رمز عبور جدید',
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password', 'placeholder': '••••••••'}),
    )

    def clean_phone_number(self) -> str:
        return _normalized_phone(self.cleaned_data['phone_number'])

    def clean_otp(self) -> str:
        return str(self.cleaned_data['otp'] or '').strip()

    def clean_password(self) -> str:
        password = self.cleaned_data['password']
        validate_password(password)
        return password

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get('password')
        confirm = cleaned.get('password_confirm')
        if password and confirm and password != confirm:
            self.add_error('password_confirm', 'رمزهای عبور وارد شده یکسان نیستند.')
        return cleaned

    def save(self):
        try:
            return confirm_password_reset(
                self.cleaned_data['phone_number'],
                self.cleaned_data['otp'],
                self.cleaned_data['password'],
            )
        except InvalidResetError as exc:
            raise DjangoValidationError(GENERIC_CONFIRM_ERROR) from exc
