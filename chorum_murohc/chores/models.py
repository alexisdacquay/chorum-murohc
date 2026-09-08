from django.db import models
from django.db.models.functions import Lower


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

    def save(self, *args, **kwargs):
        self.name = self.name.strip()
        return super().save(*args, **kwargs)
