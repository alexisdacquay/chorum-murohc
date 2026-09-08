from django.conf import settings
from django.db import models


class LedgerEntryImmutableError(RuntimeError):
    pass


class LedgerEntryQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise LedgerEntryImmutableError('Ledger entries cannot be updated.')

    def delete(self):
        raise LedgerEntryImmutableError('Ledger entries cannot be deleted.')

    def bulk_update(self, objs, fields, batch_size=None):
        raise LedgerEntryImmutableError('Ledger entries cannot be updated.')

    def bulk_create(
        self,
        objs,
        batch_size=None,
        ignore_conflicts=False,
        update_conflicts=False,
        update_fields=None,
        unique_fields=None,
    ):
        raise LedgerEntryImmutableError('Ledger entries cannot be created in bulk.')


LedgerEntryManager = models.Manager.from_queryset(LedgerEntryQuerySet)


class LedgerEntry(models.Model):
    class Reason(models.TextChoices):
        CHORE_CREDIT = 'chore_credit', 'Chore credit'
        INTEREST = 'interest', 'Interest'
        REWARD_DEBIT = 'reward_debit', 'Reward debit'
        LEVEL_DEBIT = 'level_debit', 'Level debit'

    household = models.ForeignKey(
        'identity.Household',
        on_delete=models.PROTECT,
        related_name='ledger_entries',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='ledger_entries',
    )
    amount = models.BigIntegerField()
    reason = models.CharField(max_length=32, choices=Reason.choices)
    source_type = models.CharField(max_length=100)
    source_id = models.CharField(max_length=255)
    idempotency_key = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = LedgerEntryManager()

    class Meta:
        ordering = ('-created_at', '-id')
        constraints = [  # noqa: RUF012
            models.UniqueConstraint(
                fields=('user', 'idempotency_key'),
                name='ledger_entry_user_idempotency_key_unique',
            ),
            models.CheckConstraint(
                condition=~models.Q(amount=0),
                name='ledger_entry_amount_not_zero',
            ),
            models.CheckConstraint(
                condition=models.Q(
                    reason__in=(
                        'chore_credit',
                        'interest',
                        'reward_debit',
                        'level_debit',
                    )
                ),
                name='ledger_entry_reason_valid',
            ),
        ]
        indexes = [  # noqa: RUF012
            models.Index(
                fields=('user', '-created_at', '-id'),
                name='ledger_entry_user_time_idx',
            ),
            models.Index(
                fields=('household', '-created_at', '-id'),
                name='ledger_entry_hh_time_idx',
            ),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise LedgerEntryImmutableError('Ledger entries cannot be updated.')
        kwargs['force_insert'] = True
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise LedgerEntryImmutableError('Ledger entries cannot be deleted.')
