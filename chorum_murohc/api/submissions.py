"""Submission endpoints: a child attests, and a parent reads and decides
the household's pending queue. Four routes under `/api/v1/`.

`GET/POST submissions/`, same-origin session authenticated, child-only.

- `POST` is the attestation itself: a child asserts one active own-household
  chore is done, optionally with a short note, and the row starts pending.
  This route never credits the ledger and never resolves anything; deciding
  a submission is the separate contract below.
- `GET` returns the caller's own pending submissions only, so the browser can
  show "pending review" instead of letting a child re-attempt a chore whose
  first attestation nobody has decided yet. It is deliberately not a full
  history: `_docs/design.md`'s permission matrix reserves the household
  pending queue for the parent-side `GET approvals/` contract below, and a
  decided-submission archive is a future screen's decision, not this one's.

`GET approvals/` (T044, issue #44): the parent-only, paginated, household
pending queue - every submission still awaiting a decision, newest first.

`GET approving-parents/` (issue #44, supporting T047): child-only. The
household's active parents who currently hold a PIN, so the child device can
show real names to choose from before asking for one's PIN, exactly as
`_docs/approval-authentication.md` requires. A parent with no PIN is left off
the list entirely; a locked one stays listed as `available: false`.

`POST submissions/<pk>/decide/` (T046, issue #44): one mutation for both
approval paths named in `_docs/approval-authentication.md`. All state, ledger
and audit work is delegated to `chorum_murohc.submissions.services.
decide_submission`; this module's job is authority, HTTP shape, and mapping
that service's outcomes onto responses. A submission that is missing, in
another household, or no longer pending reads as one identical 404, so a
retried decide request is refused the same safe way a row that never existed
is - never a second credit, matching `api/redemptions.py`'s action routes.

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
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.generics import ListAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from chorum_murohc.api.permissions import (
    PERMISSION_DENIED_DETAIL,
    IsHouseholdChild,
    IsHouseholdParent,
)
from chorum_murohc.api.session import resolve_active_membership
from chorum_murohc.audit.models import AuditEvent
from chorum_murohc.chores.models import Chore
from chorum_murohc.identity.models import Membership, ParentPin
from chorum_murohc.identity.services import LOCKOUT_DURATION, PinVerificationResult
from chorum_murohc.submissions.models import Submission
from chorum_murohc.submissions.services import (
    DECISION_APPROVE,
    DECISION_REJECT,
    SubmissionAuthorityError,
    SubmissionPinError,
    decide_submission,
)

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

# The two generic PIN-decision failures. Neither names a parent, a household,
# or which rule refused the value, matching `_docs/approval-authentication.md`
# ("What is said and recorded"): a wrong PIN, an unknown parent, a parent with
# no PIN and a stale selection are one generic failure, and a lockout says
# only that attempts are refused and when they resume. `LOCKOUT_MINUTES` is
# the fixed window every lock uses, so stating it needs no per-attempt read of
# a parent's own lock expiry - itself state this response must never reveal.
LOCKOUT_MINUTES = int(LOCKOUT_DURATION.total_seconds() // 60)
PIN_INCORRECT_DETAIL = 'That PIN was not accepted.'
PIN_LOCKED_DETAIL = f'Too many attempts. Try again in {LOCKOUT_MINUTES} minutes.'
APPROVING_PARENT_REQUIRED_DETAIL = 'Select which parent is approving.'
DECISION_MAX_LENGTH = 10
REASON_MAX_LENGTH = 200

IsHouseholdParentOrChild = IsHouseholdParent | IsHouseholdChild


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
        membership = resolve_active_membership(request.user, request)
        return None if membership is None else membership.household

    def require_child_membership(self):
        """Re-resolve the acting child, for use inside a write transaction."""
        membership = resolve_active_membership(self.request.user, self.request)
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


# --- the parent's pending queue (T044) ------------------------------------


class PendingApprovalPagination(PageNumberPagination):
    """DRF's built-in page-number scheme, sized for this endpoint only,
    matching `api/audit.py`'s own scoped pagination rather than the
    project's shared `REST_FRAMEWORK` settings (there is no default there)."""

    page_size = 25
    page_size_query_param = 'page_size'
    max_page_size = 100


class PendingApprovalSerializer(serializers.ModelSerializer):
    """What a parent sees for one pending submission: who submitted it, the
    chore snapshot, the point value it is worth, and when it was submitted.
    No note field is withheld here - a parent already sees a child's own note
    on the equivalent child-side shape, so there is nothing more sensitive to
    add for the parent side."""

    child_id = serializers.IntegerField(read_only=True)
    child_username = serializers.CharField(source='child.username', read_only=True)

    class Meta:
        model = Submission
        fields = (
            'id',
            'child_id',
            'child_username',
            'chore',
            'chore_name',
            'chore_points',
            'note',
            'created_at',
        )
        read_only_fields = fields


class PendingApprovalListView(ListAPIView):
    """`GET /api/v1/approvals/`: the caller's own-household pending queue,
    parent-only, newest first, natively paginated."""

    http_method_names = ('get', 'head', 'options')
    renderer_classes = (JSONRenderer,)
    authentication_classes = (SessionAuthentication,)
    permission_classes = (IsHouseholdParent,)
    serializer_class = PendingApprovalSerializer
    pagination_class = PendingApprovalPagination

    def initial(self, request, *args, **kwargs):
        if request.method.lower() not in self.http_method_names:
            self.http_method_not_allowed(request)
        super().initial(request, *args, **kwargs)

    def get_permission_household(self, request):
        membership = resolve_active_membership(request.user, request)
        return None if membership is None else membership.household

    def get_queryset(self):
        household = self.get_permission_household(self.request)
        if household is None:
            return Submission.objects.none()
        return Submission.objects.filter(
            household=household, status=Submission.Status.PENDING
        ).order_by('-created_at', '-id')


# --- the child-device parent picker (issue #44, supporting T047) ----------


class ApprovingParentListView(APIView):
    """`GET /api/v1/approving-parents/`: child-only.

    The household's active parents who currently hold a PIN, matching
    `_docs/approval-authentication.md`'s "The child-device list holds that
    household's active parents who have a PIN; a locked one stays listed,
    marked temporarily unavailable." A parent with no PIN at all is left off
    the list entirely rather than shown as unavailable, and nothing here ever
    states whether a listed parent's PIN is merely wrong versus locked - only
    the later decide attempt distinguishes those, and even then only by its
    own two fixed, generic details.
    """

    http_method_names = ('get', 'head', 'options')
    renderer_classes = (JSONRenderer,)
    authentication_classes = (SessionAuthentication,)
    permission_classes = (IsHouseholdChild,)

    def initial(self, request, *args, **kwargs):
        if request.method.lower() not in self.http_method_names:
            self.http_method_not_allowed(request)
        super().initial(request, *args, **kwargs)

    def get_permission_household(self, request):
        membership = resolve_active_membership(request.user, request)
        return None if membership is None else membership.household

    def get(self, request):
        household = self.get_permission_household(request)
        if household is None:
            return Response([])

        now = timezone.now()
        memberships = (
            Membership.objects.filter(
                household=household,
                role=Membership.Role.PARENT,
                user__is_active=True,
            )
            .select_related('user')
            .order_by('user__username', 'user_id')
        )
        pins_by_user_id = dict(
            ParentPin.objects.filter(
                user_id__in=[membership.user_id for membership in memberships]
            ).values_list('user_id', 'locked_until')
        )

        body = [
            {
                'id': membership.user_id,
                'username': membership.user.username,
                'available': pins_by_user_id[membership.user_id] is None
                or pins_by_user_id[membership.user_id] <= now,
            }
            for membership in memberships
            if membership.user_id in pins_by_user_id
        ]
        return Response(body)


# --- deciding one submission (T046) ---------------------------------------


class SubmissionDecisionRequestSerializer(serializers.Serializer):
    """The only writable body for `POST submissions/<pk>/decide/`.

    `approving_parent` is optional here because whether it is required
    depends on which device is calling - a parent's own session needs none,
    a child's session needs one - and that is a caller-role question the
    view answers, not a fixed field-presence rule this serializer can state
    on its own.
    """

    decision = serializers.ChoiceField(choices=(DECISION_APPROVE, DECISION_REJECT))
    pin = serializers.CharField(
        allow_blank=False,
        max_length=1000,
        trim_whitespace=False,
        write_only=True,
    )
    approving_parent = serializers.IntegerField(required=False, min_value=1)
    reason = serializers.CharField(
        required=False,
        allow_blank=True,
        default='',
        max_length=REASON_MAX_LENGTH,
        trim_whitespace=True,
    )


class SubmissionDecisionResponseSerializer(serializers.ModelSerializer):
    """The exact decided-submission shape returned to either device."""

    class Meta:
        model = Submission
        fields = (
            'id',
            'chore_name',
            'chore_points',
            'note',
            'status',
            'rejection_reason',
            'created_at',
            'decided_at',
        )
        read_only_fields = fields


class SubmissionDecisionView(APIView):
    """`POST /api/v1/submissions/<pk>/decide/`: approve or reject.

    All state, ledger and audit work happens in
    `chorum_murohc.submissions.services.decide_submission`, re-validated
    inside its own transaction immediately before writing; this view holds
    no transaction and no ledger write of its own, exactly as
    `api/redemptions.py`'s action views delegate to `rewards.services`.
    """

    http_method_names = ('post', 'options')
    renderer_classes = (JSONRenderer,)
    authentication_classes = (SessionAuthentication,)
    permission_classes = (IsHouseholdParentOrChild,)

    def initial(self, request, *args, **kwargs):
        if request.method.lower() not in self.http_method_names:
            self.http_method_not_allowed(request)
        super().initial(request, *args, **kwargs)

    def get_permission_household(self, request):
        membership = resolve_active_membership(request.user, request)
        return None if membership is None else membership.household

    def post(self, request, pk):
        membership = resolve_active_membership(request.user, request)
        if membership is None or membership.role not in (
            Membership.Role.PARENT,
            Membership.Role.CHILD,
        ):
            raise PermissionDenied(PERMISSION_DENIED_DETAIL)

        serializer = SubmissionDecisionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data

        approving_parent_id = values.get('approving_parent')
        if membership.role == Membership.Role.CHILD and approving_parent_id is None:
            raise serializers.ValidationError(
                {'approving_parent': [APPROVING_PARENT_REQUIRED_DETAIL]}
            )

        try:
            submission = decide_submission(
                household=membership.household,
                acting_user=request.user,
                submission_id=pk,
                decision=values['decision'],
                pin=values['pin'],
                approving_parent_id=approving_parent_id,
                reason=values['reason'],
            )
        except Submission.DoesNotExist:
            # Missing, foreign-household, and already-decided rows alike: a
            # stale or repeated decision is refused the same way a row that
            # never existed is, and neither answer confirms which.
            raise NotFound() from None
        except (Membership.DoesNotExist, SubmissionAuthorityError):
            raise PermissionDenied(PERMISSION_DENIED_DETAIL) from None
        except SubmissionPinError as error:
            detail = (
                PIN_LOCKED_DETAIL
                if error.result is PinVerificationResult.LOCKED
                else PIN_INCORRECT_DETAIL
            )
            raise serializers.ValidationError({'pin': [detail]}) from None

        return Response(SubmissionDecisionResponseSerializer(submission).data)
