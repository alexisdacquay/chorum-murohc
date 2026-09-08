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


class Chore(models.Model):
    household = models.ForeignKey(
        'identity.Household',
        on_delete=models.PROTECT,
        related_name='chores',
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
                name='chore_hh_name_ci_unique',
            ),
            models.CheckConstraint(
                condition=models.Q(points__gte=1),
                name='chore_points_positive',
            ),
            models.CheckConstraint(
                condition=~models.Q(name=''),
                name='chore_name_not_blank',
            ),
        ]
        indexes = [  # noqa: RUF012
            models.Index(
                fields=('household', 'is_active', 'name'),
                name='chore_hh_active_name_idx',
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
