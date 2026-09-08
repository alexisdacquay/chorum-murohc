from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.functions import Lower


def _is_fractional(value):
    """Report a value Django's IntegerField would silently truncate to a whole one."""
    if value is None or isinstance(value, int | str):
        return False
    try:
        return int(value) != value
    except (OverflowError, TypeError, ValueError):
        return False


class Reward(models.Model):
    """One catalogue item a parent offers: a name and its point cost.

    Shaped exactly like `chorum_murohc.chores.models.Chore`: the same
    household scoping, case-insensitive per-household name uniqueness,
    positive-point check, active/inactive lifecycle, and fractional-point
    guard. Reuse, not reinvention, for two nearly identical domain concepts.
    """

    household = models.ForeignKey(
        'identity.Household',
        on_delete=models.PROTECT,
        related_name='rewards',
    )
    name = models.CharField(max_length=100)
    points = models.IntegerField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('name', 'id')
        constraints = [  # noqa: RUF012
            models.UniqueConstraint(
                Lower('name'),
                'household',
                name='reward_hh_name_ci_unique',
            ),
            models.CheckConstraint(
                condition=models.Q(points__gte=1),
                name='reward_points_positive',
            ),
            models.CheckConstraint(
                condition=~models.Q(name=''),
                name='reward_name_not_blank',
            ),
        ]
        indexes = [  # noqa: RUF012
            models.Index(
                fields=('household', 'is_active', 'name'),
                name='reward_hh_active_name_idx',
            ),
        ]

    def clean_fields(self, exclude=None):
        # IntegerField.to_python() truncates 2.5 to 2, so a fractional point value
        # has to be caught before field validation coerces the fraction away.
        errors = {}
        if (exclude is None or 'points' not in exclude) and _is_fractional(self.points):
            errors['points'] = ['Points must be a whole number.']
        try:
            super().clean_fields(exclude=exclude)
        except ValidationError as invalid:
            errors = invalid.update_error_dict(errors)
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.name = self.name.strip()
        return super().save(*args, **kwargs)


class RedemptionTransitionError(RuntimeError):
    pass


class RedemptionQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise RedemptionTransitionError(
            'Redemptions can only change through Redemption.save().'
        )


RedemptionManager = models.Manager.from_queryset(RedemptionQuerySet)


class Redemption(models.Model):
    """One child's spend of points on one reward, and its outcome.

    Shaped like `chorum_murohc.submissions.models.Submission`: created only
    `pending`, exactly two legal transitions out of pending, both terminal,
    and every transition after creation must go through `save()` with an
    acting parent recorded, never through a queryset `update()`.

    `reward_name` and `reward_points` are a snapshot taken at redemption, so
    a later edit or deletion of the `Reward` catalogue row never changes what
    this record says the child spent, exactly as `Submission` snapshots a
    chore's name and points.
    """

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        FULFILLED = 'fulfilled', 'Fulfilled'
        CANCELLED = 'cancelled', 'Cancelled'

    # Every legal transition starts from pending. Nothing else is allowed:
    # deciding twice, reversing a decision, or editing a decided row all deny.
    _LEGAL_NEXT_STATUSES = (Status.FULFILLED, Status.CANCELLED)

    household = models.ForeignKey(
        'identity.Household',
        on_delete=models.PROTECT,
        related_name='redemptions',
    )
    child = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='redemptions',
    )
    # Nullable: a decided redemption survives its reward's deletion with a
    # null reference, exactly as a decided submission survives its chore's.
    reward = models.ForeignKey(
        'rewards.Reward',
        on_delete=models.SET_NULL,
        null=True,
        related_name='redemptions',
    )
    reward_name = models.CharField(max_length=100)
    reward_points = models.IntegerField()
    status = models.CharField(
        max_length=9,
        choices=Status.choices,
        default=Status.PENDING,
    )
    idempotency_key = models.CharField(max_length=255)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='decided_redemptions',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    objects = RedemptionManager()

    class Meta:
        ordering = ('-created_at', '-id')
        constraints = [  # noqa: RUF012
            models.UniqueConstraint(
                fields=('child', 'idempotency_key'),
                name='redemption_child_idempotency_key_unique',
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=('pending', 'fulfilled', 'cancelled')),
                name='redemption_status_valid',
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(status='pending', decided_at__isnull=True)
                    | (~models.Q(status='pending') & models.Q(decided_at__isnull=False))
                ),
                name='redemption_decision_matches_status',
            ),
            models.CheckConstraint(
                condition=models.Q(status='pending', decided_by__isnull=True)
                | ~models.Q(status='pending'),
                name='redemption_decided_by_unset_while_pending',
            ),
            models.CheckConstraint(
                condition=models.Q(reward_points__gte=1),
                name='redemption_reward_points_positive',
            ),
        ]
        indexes = [  # noqa: RUF012
            models.Index(
                fields=('household', 'status', '-created_at'),
                name='redemption_hh_status_idx',
            ),
            models.Index(
                fields=('child', 'status', '-created_at'),
                name='redemption_child_status_idx',
            ),
        ]

    def save(self, *args, **kwargs):
        if self._state.adding:
            if self.status != self.Status.PENDING:
                raise RedemptionTransitionError(
                    'A redemption can only be created pending.'
                )
            return super().save(*args, **kwargs)

        previous_status = (
            Redemption.objects.filter(pk=self.pk)
            .values_list('status', flat=True)
            .first()
        )
        if previous_status != self.Status.PENDING:
            raise RedemptionTransitionError('A decided redemption cannot be changed.')
        if self.status not in self._LEGAL_NEXT_STATUSES:
            raise RedemptionTransitionError(
                f'{previous_status} cannot transition to {self.status}.'
            )
        if self.decided_by_id is None:
            raise RedemptionTransitionError(
                'A transition out of pending must record who acted.'
            )
        return super().save(*args, **kwargs)
