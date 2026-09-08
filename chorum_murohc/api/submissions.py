"""The child completion-attestation endpoint: one route under `/api/v1/`.

`GET/POST submissions/`, same-origin session authenticated, child-only.

- `POST` is the attestation itself: a child asserts one active own-household
  chore is done, optionally with a short note, and the row starts pending. A
  parent's later decision is a separate, not-yet-built endpoint (T044 to
  T046); this one never credits the ledger and never resolves anything.
- `GET` returns the caller's own pending submissions only, so the browser can
  show "pending review" instead of letting a child re-attempt a chore whose
  first attestation nobody has decided yet. It is deliberately not a full
  history: `_docs/design.md`'s permission matrix reserves the household
  pending queue for the parent-side T044 contract, and a decided-submission
  archive is a future screen's decision, not this one's.

Authority is never taken from the client. The household and the acting child
both come from `resolve_active_membership`, never from a body, query string,
path or header, so a `chore` id from another household reads as an ordinary
404 rather than a denial that confirms the row exists, and nobody can submit
as another child. Membership is re-resolved inside the write transaction, so a
membership revoked a moment ago cannot slip a submission through.

Idempotency is a client-supplied key, exactly as `_docs/design.md`'s duplicate
-request invariant asks for: a network retry of the same confirm click carries
the same key and gets back the same submission rather than a second row or an
error. A key reused for a different chore is refused; a second, distinct
attempt at a chore that already has one pending is refused by the model's own
`submission_one_pending_per_child_chore` constraint. Both read as one compact
400, never a 500, matching the chore-pool endpoints' `duplicate_name_error`.
"""

from django.db import IntegrityError, transaction
from rest_framework import serializers, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from chorum_murohc.api.permissions import PERMISSION_DENIED_DETAIL, IsHouseholdChild
from chorum_murohc.api.session import resolve_active_membership
from chorum_murohc.audit.models import AuditEvent
from chorum_murohc.chores.models import Chore
from chorum_murohc.identity.models import Membership
from chorum_murohc.submissions.models import Submission

# The audit target and the one code this endpoint writes.
AUDIT_TARGET_TYPE = 'submission'
AUDIT_CREATE = 'submission.create'

NOTE_MAX_LENGTH = 280
IDEMPOTENCY_KEY_MAX_LENGTH = 255

# The two details a duplicate can produce. Neither names another household,
# another child, or the chore's own state.
DUPLICATE_PENDING_DETAIL = (
    'You already have a pending submission for this chore. '
    'Wait for it to be reviewed before submitting again.'
)
IDEMPOTENCY_KEY_REUSED_DETAIL = (
    'This confirmation was already used for a different chore. Try again.'
)


class SubmissionSerializer(serializers.ModelSerializer):
    """The read shape: what a child may see about their own submission."""

    class Meta:
        model = Submission
        fields = (
            'id',
            'chore',
            'chore_name',
            'chore_points',
            'note',
            'status',
            'created_at',
        )
        read_only_fields = fields


class SubmissionCreateSerializer(serializers.Serializer):
    """The only writable body: which chore, and an optional note.

    `household` and `child` are never accepted here: the household comes
    from the caller's own membership and the child is always the caller, so
    no body can attest on another child's behalf or in another household.
    """

    chore = serializers.IntegerField()
    note = serializers.CharField(
        required=False,
        allow_blank=True,
        default='',
        max_length=NOTE_MAX_LENGTH,
        trim_whitespace=True,
    )
    idempotency_key = serializers.CharField(
        allow_blank=False,
        max_length=IDEMPOTENCY_KEY_MAX_LENGTH,
        trim_whitespace=True,
    )


class SubmissionListView(APIView):
    """`GET` and `POST /api/v1/submissions/`, child-only both ways.

    Reading is not offered to a parent here at all: the permission matrix
    gives the parent side its own household pending queue through T044, a
    different contract this task does not build.
    """

    renderer_classes = (JSONRenderer,)
    authentication_classes = (SessionAuthentication,)
    permission_classes = (IsHouseholdChild,)
    http_method_names = ('get', 'head', 'post', 'options')

    def initial(self, request, *args, **kwargs):
        if request.method.lower() not in self.http_method_names:
            self.http_method_not_allowed(request)
        super().initial(request, *args, **kwargs)

    def get_permission_household(self, request):
        """The one household the caller may act in, or `None`."""
        membership = resolve_active_membership(request.user)
        return None if membership is None else membership.household

    def require_child_membership(self):
        """Re-resolve the acting child, for use inside a write transaction."""
        membership = resolve_active_membership(self.request.user)
        if membership is None or membership.role != Membership.Role.CHILD:
            raise PermissionDenied(PERMISSION_DENIED_DETAIL)
        return membership

    def get_active_chore(self, household, chore_id):
        """The one active chore of `household` matching `chore_id`, or 404.

        An inactive chore and a chore of another household are the same
        generic 404: neither confirms the other, matching `chores.get_chore`.
        """
        chore = Chore.objects.filter(
            household=household, is_active=True, pk=chore_id
        ).first()
        if chore is None:
            raise NotFound()
        return chore

    def get(self, request):
        household = self.get_permission_household(request)
        submissions = Submission.objects.filter(
            household=household,
            child=request.user,
            status=Submission.Status.PENDING,
        ).order_by('-created_at', '-id')
        return Response(SubmissionSerializer(submissions, many=True).data)

    def post(self, request):
        serializer = SubmissionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            with transaction.atomic():
                membership = self.require_child_membership()
                chore = self.get_active_chore(
                    membership.household, serializer.validated_data['chore']
                )
                submission = Submission.objects.create(
                    household=membership.household,
                    child=membership.user,
                    chore=chore,
                    chore_name=chore.name,
                    chore_points=chore.points,
                    note=serializer.validated_data['note'],
                    idempotency_key=serializer.validated_data['idempotency_key'],
                )
                AuditEvent.objects.create(
                    household=membership.household,
                    actor=membership.user,
                    action=AUDIT_CREATE,
                    target_type=AUDIT_TARGET_TYPE,
                    target_id=str(submission.pk),
                    context={
                        'actor_id': membership.user_id,
                        'submission_id': submission.pk,
                        'chore_id': chore.pk,
                        'chore_name': chore.name,
                        'chore_points': chore.points,
                        'note': submission.note,
                    },
                )
                body = SubmissionSerializer(submission).data
        except IntegrityError as error:
            return self._duplicate_response(error, serializer, chore)
        return Response(body, status=status.HTTP_201_CREATED)

    def _duplicate_response(self, error, serializer, chore):
        """Turn a unique-constraint hit into the matching compact 400 or 200.

        The atomic block above has already rolled back by the time this
        runs, so a lookup here reads a clean, committed state rather than a
        poisoned transaction. Which of the table's two unique constraints
        fired is read back from the data rather than parsed out of the
        driver's own error text: SQLite reports a plain multi-column unique
        constraint by its column names, never its name, so a string check
        that works against PostgreSQL would silently never match here.
        """
        idempotency_key = serializer.validated_data['idempotency_key']
        existing = Submission.objects.filter(
            child=self.request.user, idempotency_key=idempotency_key
        ).first()
        if existing is not None:
            if existing.chore_id == chore.pk:
                # The exact same confirmation, retried. Answer with the
                # submission it already made instead of making a second one.
                return Response(
                    SubmissionSerializer(existing).data, status=status.HTTP_200_OK
                )
            raise serializers.ValidationError(
                {'idempotency_key': [IDEMPOTENCY_KEY_REUSED_DETAIL]}
            )

        if Submission.objects.filter(
            child=self.request.user, chore=chore, status=Submission.Status.PENDING
        ).exists():
            raise serializers.ValidationError({'chore': [DUPLICATE_PENDING_DETAIL]})

        # Neither known constraint explains it: a real fault, not a duplicate.
        raise error
