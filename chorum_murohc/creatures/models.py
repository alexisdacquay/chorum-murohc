"""Creature state: one row per child, holding the line they picked.

The catalogue itself is not stored. Seven lines and twenty-eight drawings are
code, identical for every household and changeable only by committing a new
drawing (see `catalogue.py`), so putting them in the database would add a
loader, a migration and a drift risk and buy nothing.

The one fact that IS household data is which line a child picked, and that is
this single row. It is written once, at first sign-in, and never rewritten:
the forms a child has unlocked are a pure function of their level, which
`chorum_murohc.progression` already computes from the ledger, so there is no
progress here to store or to corrupt.
"""

from django.conf import settings
from django.db import models

from chorum_murohc.creatures.catalogue import LINE_SLUGS

# Long enough for every slug in the catalogue with room to spare, and short
# enough that a stored value stays a slug rather than free text.
LINE_SLUG_MAX_LENGTH = 32


class CreatureSelection(models.Model):
    household = models.ForeignKey(
        'identity.Household',
        on_delete=models.PROTECT,
        related_name='creature_selections',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='creature_selections',
    )
    line_slug = models.CharField(max_length=LINE_SLUG_MAX_LENGTH)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [  # noqa: RUF012
            models.UniqueConstraint(
                fields=('household', 'user'),
                name='creatures_creatureselection_household_user_unique',
            ),
            # The database refuses a slug the catalogue does not define, so a
            # row can never point at a drawing that does not exist. Retiring
            # or adding a line therefore needs a migration, which is the
            # point: the drawings are committed files, not configuration.
            models.CheckConstraint(
                condition=models.Q(line_slug__in=LINE_SLUGS),
                name='creatures_creatureselection_line_slug_known',
            ),
        ]
