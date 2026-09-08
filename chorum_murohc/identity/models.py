from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    pass


class Household(models.Model):
    name = models.CharField(max_length=150)
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through='Membership',
        through_fields=('household', 'user'),
        related_name='households',
    )


class Membership(models.Model):
    class Role(models.TextChoices):
        PARENT = 'parent', 'Parent'
        CHILD = 'child', 'Child'

    household = models.ForeignKey(
        Household,
        on_delete=models.CASCADE,
        related_name='memberships',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='household_memberships',
    )
    role = models.CharField(max_length=6, choices=Role.choices)

    class Meta:
        constraints = [  # noqa: RUF012
            models.UniqueConstraint(
                fields=('household', 'user'),
                name='identity_membership_household_user_unique',
            ),
            models.CheckConstraint(
                condition=models.Q(role__in=('parent', 'child')),
                name='identity_membership_role_valid',
            ),
        ]


class ParentPin(models.Model):
    """One parent's hashed approval PIN, and its lockout state.

    Belongs to a user, never to a household (`_docs/approval-authentication.md`:
    "A PIN belongs to one parent user account, not to a household"), so this
    model carries no household reference. `pin_hash` is produced by Django's
    own password hasher (`django.contrib.auth.hashers`), exactly like
    `User.password`; the raw PIN is never stored and this field is never
    serialised in an API response or placed in an audit event.

    `failed_attempts` and `locked_until` are the whole of the lockout state
    the approved policy needs: a per-parent, database-held counter and expiry,
    read and written under a row lock (`chorum_murohc.identity.services`) so that
    concurrent verification attempts cannot lose an increment.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='parent_pin',
    )
    pin_hash = models.CharField(max_length=255)
    # A plain SmallIntegerField, like `Chore.points`: the non-negative rule is
    # one explicit named constraint below rather than the framework's own
    # implicit one, so the schema states its own invariant.
    failed_attempts = models.SmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [  # noqa: RUF012
            models.CheckConstraint(
                condition=models.Q(failed_attempts__gte=0),
                name='identity_parentpin_failed_attempts_not_negative',
            ),
        ]
