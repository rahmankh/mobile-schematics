"""Grant a paid subscription period. Called only after payment verify() succeeds."""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from .models import Plan, UserSubscription


def fulfill_subscription(user, plan: Plan) -> UserSubscription:
    """
    Activate `plan` for `user`.

    If an ACTIVE subscription still covers now, the new period starts at that
    end_date (stacking / renewal). Never call this from a checkout view.
    """
    now = timezone.now()
    active = (
        UserSubscription.objects.filter(
            user=user,
            status=UserSubscription.StatusChoices.ACTIVE,
            end_date__gt=now,
        )
        .order_by('-end_date')
        .first()
    )
    start_date = active.end_date if active else now
    return UserSubscription.objects.create(
        user=user,
        plan=plan,
        start_date=start_date,
        end_date=start_date + timedelta(days=plan.duration_days),
        status=UserSubscription.StatusChoices.ACTIVE,
    )
