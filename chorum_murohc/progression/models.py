"""Progression state: one row per child, holding nothing but a marker.

Issue #61 decided the level itself is never stored: it is a pure function of
a child's lifetime points earned, read fresh from the ledger every time
(`chorum_murohc.progression.services.level_for_lifetime_points`). "Levelling
is computed from the ledger rather than stored as a mutable counter."

The one thing that policy still needs persisted is which level a child has
already been shown the celebration for, so "the level-up is shown to the
child once, the first time they see it" and never replayed on a later visit.
`LevelAcknowledgement.highest_level_shown` is that marker and nothing else:
it is never read to answer "what level is this child", only to answer "has
this child already seen this one".
"""

from django.conf import settings
from django.db import models

# The highest level this app currently supports (ten lifetime-points
# thresholds; see `services.LEVEL_THRESHOLDS`). Kept here, not imported from
# `services`, so the migration this produces never depends on that module
# changing shape.
MAX_LEVEL = 10


class LevelAcknowledgement(models.Model):
    household = models.ForeignKey(
        'identity.Household',
        on_delete=models.PROTECT,
        related_name='level_acknowledgements',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='level_acknowledgements',
    )
    highest_level_shown = models.PositiveSmallIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [  # noqa: RUF012
            models.UniqueConstraint(
                fields=('household', 'user'),
                name='progression_levelacknowledgement_household_user_unique',
            ),
            models.CheckConstraint(
                condition=models.Q(highest_level_shown__gte=0)
                & models.Q(highest_level_shown__lte=MAX_LEVEL),
                name='progression_levelacknowledgement_shown_level_range',
            ),
        ]
