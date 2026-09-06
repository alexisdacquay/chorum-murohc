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
