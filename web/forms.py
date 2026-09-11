"""Session-login form for the HTML catalog (phone number, not email)."""

from django.contrib.auth.forms import AuthenticationForm
from django import forms


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
