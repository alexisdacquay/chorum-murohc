from django.conf import settings
from django.db import models


class SubmissionTransitionError(RuntimeError):
    pass


class SubmissionQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise SubmissionTransitionError(
            'Submissions can only change through Submission.save().'
        )


SubmissionManager = models.Manager.from_queryset(SubmissionQuerySet)


class Submission(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'
        WITHDRAWN = 'withdrawn', 'Withdrawn'

    # Every legal transition starts from pending. Nothing else is allowed:
    # deciding twice, reversing a decision, or editing a decided row all deny.
    _LEGAL_NEXT_STATUSES = (Status.APPROVED, Status.REJECTED, Status.WITHDRAWN)

    household = models.ForeignKey(
        'identity.Household',
        on_delete=models.PROTECT,
        related_name='submissions',
    )
    child = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='submissions',
    )
    # Nullable: a decided submission survives its chore's deletion with a null
    # reference. A pending submission is removed together with its chore by
    # the chore-delete service, never left dangling here.
    chore = models.ForeignKey(
        'chores.Chore',
        on_delete=models.SET_NULL,
        null=True,
        related_name='submissions',
    )
    chore_name = models.CharField(max_length=100)
    chore_points = models.IntegerField()
    status = models.CharField(
        max_length=9,
        choices=Status.choices,
        default=Status.PENDING,
    )
    idempotency_key = models.CharField(max_length=255)
    rejection_reason = models.CharField(max_length=200, blank=True, default='')
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='decided_submissions',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    objects = SubmissionManager()

    class Meta:
        ordering = ('-created_at', '-id')
        constraints = [  # noqa: RUF012
            models.UniqueConstraint(
                fields=('child', 'idempotency_key'),
                name='submission_child_idempotency_key_unique',
            ),
            models.UniqueConstraint(
                fields=('child', 'chore'),
                condition=models.Q(status='pending'),
                name='submission_one_pending_per_child_chore',
            ),
            models.CheckConstraint(
                condition=models.Q(
                    status__in=('pending', 'approved', 'rejected', 'withdrawn')
                ),
                name='submission_status_valid',
            ),
            # decided_by is allowed to go null on a decided row later, when the
            # deciding parent is deleted (SET_NULL, matching AuditEvent.actor),
            # so only decided_at -- never touched after the transition -- is
            # tied to status here. decided_by is still required not-null at the
            # moment of the transition, by save() below.
            models.CheckConstraint(
                condition=(
                    models.Q(status='pending', decided_at__isnull=True)
                    | (~models.Q(status='pending') & models.Q(decided_at__isnull=False))
                ),
                name='submission_decision_matches_status',
            ),
            models.CheckConstraint(
                condition=models.Q(status='pending', decided_by__isnull=True)
                | ~models.Q(status='pending'),
                name='submission_decided_by_unset_while_pending',
            ),
            models.CheckConstraint(
                condition=models.Q(chore_points__gte=1),
                name='submission_chore_points_positive',
            ),
        ]
        indexes = [  # noqa: RUF012
            models.Index(
                fields=('household', 'status', '-created_at'),
                name='submission_hh_status_idx',
            ),
            models.Index(
                fields=('child', 'status', '-created_at'),
                name='submission_child_status_idx',
            ),
        ]

    def save(self, *args, **kwargs):
        if self._state.adding:
            if self.status != self.Status.PENDING:
                raise SubmissionTransitionError(
                    'A submission can only be created pending.'
                )
            return super().save(*args, **kwargs)

        previous_status = (
            Submission.objects.filter(pk=self.pk)
            .values_list('status', flat=True)
            .first()
        )
        if previous_status != self.Status.PENDING:
            raise SubmissionTransitionError('A decided submission cannot be changed.')
        if self.status not in self._LEGAL_NEXT_STATUSES:
            raise SubmissionTransitionError(
                f'{previous_status} cannot transition to {self.status}.'
            )
        if self.decided_by_id is None:
            raise SubmissionTransitionError(
                'A transition out of pending must record who acted.'
            )
        return super().save(*args, **kwargs)
