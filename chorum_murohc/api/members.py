"""Household account directory: list, create, edit, deactivate, reactivate
and delete the accounts of one household.

Seven routes under `/api/v1/household-members/`, all same-origin session
authenticated, parent-only and scoped to the one household the caller is a
live parent of. Unlike the chore pool, a child is denied every route here,
including read: the permission matrix in `_docs/design.md` marks the whole
directory "Deny" for a child.

- `GET household-members/` lists members, active only by default, both
  states behind `?include_inactive=true`.
- `POST household-members/` creates a member: a username, a password and a
  role of exactly `parent` or `child`.
- `GET`, `PATCH` and `DELETE household-members/<pk>/` read, edit and remove
  one member. `<pk>` is the target user's id, not a membership row id.
- `POST household-members/<pk>/deactivate/` and `.../reactivate/` move a
  member between the two login states.

This task adds no model and no migration. `identity.User` and
`identity.Membership` already carry every field the contract needs -
`date_joined` stands in for a created-at timestamp - so the directory is
built entirely from the existing schema.

`_docs/retention-policy.md`, "Who may act", governs every mutation here:
only a live parent of the target's household may act, and the actor may
never act on their own account through this API - self-service belongs to a
future settings screen, not this one. A household must always keep one
active parent; deactivating, deleting or demoting the last one denies inside
the same transaction as the write it guards.

That guard has to survive two parents racing each other, not just one parent
acting twice: two concurrent requests could each target a *different* one of
a household's last two parents and, reading the other as "still active",
both succeed and empty the household. `_lock_parents` closes that race by
locking every parent's account row, in one fixed id order, before any of
them is read - every mutation on any member acquires that same lock first,
so two overlapping requests always queue on it in the same order and the
second one always sees the first one's committed effect before it decides.

Deleting a member is real removal. `_docs/retention-policy.md` requires it
to take the member's memberships, submissions, ledger entries, rewards,
progression and creature selection with it; `Submission.child` and
`LedgerEntry.user` are already `on_delete=CASCADE`, so deleting the `User`
row does that by itself; this module only reads the counts first for the
audit event. A deletion event records those counts and the target id only,
never a username, matching the chore-delete precedent in `api/chores.py`.
"""

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from rest_framework import serializers, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from chorum_murohc.api.permissions import PERMISSION_DENIED_DETAIL, IsHouseholdParent
from chorum_murohc.api.session import resolve_active_membership
from chorum_murohc.audit.models import AuditEvent
from chorum_murohc.identity.models import Membership, User
from chorum_murohc.ledger.models import LedgerEntry
from chorum_murohc.submissions.models import Submission

# The audit target these endpoints write, and the six codes the retention
# policy lists for an account. An edit that changes the role writes
# `account.role_change` instead of `account.update`, even when other fields
# changed in the same request, so the more sensitive change is never buried
# under the generic code.
AUDIT_TARGET_TYPE = 'account'
AUDIT_CREATE = 'account.create'
AUDIT_UPDATE = 'account.update'
AUDIT_ROLE_CHANGE = 'account.role_change'
AUDIT_DEACTIVATE = 'account.deactivate'
AUDIT_REACTIVATE = 'account.reactivate'
AUDIT_DELETE = 'account.delete'

LAST_PARENT_DETAIL = 'The household must keep at least one active parent.'
DUPLICATE_USERNAME_DETAIL = 'A user with that username already exists.'

# The exact query string that widens the directory to both login states.
INCLUDE_INACTIVE_PARAMETER = 'include_inactive'
INCLUDE_INACTIVE_VALUE = 'true'


def _lock_parents(household):
    """Lock every parent account of `household`, in a fixed id order.

    Every mutating route calls this first, whatever its own target, so two
    concurrent requests against the same household always queue on the same
    rows in the same order and can never deadlock each other. `select_related`
    plus `select_for_update` locks the joined `User` row too, on PostgreSQL,
    which is what lets the count below read a fresh `is_active`.
    """
    return list(
        Membership.objects.select_for_update()
        .filter(household=household, role=Membership.Role.PARENT)
        .select_related('user')
        .order_by('user_id')
    )


def _deny_if_would_remove_last_active_parent(locked_parents, excluded_user_id):
    remaining = sum(
        1
        for membership in locked_parents
        if membership.user.is_active and membership.user_id != excluded_user_id
    )
    if remaining == 0:
        raise ValidationError({'detail': LAST_PARENT_DETAIL})


def _clean_username(value, *, instance=None):
    """Apply the model field's own format rules, then its uniqueness rule.

    Routed through `User._meta.get_field('username')` rather than a DRF
    `max_length` or a hand-written regex, exactly as `bootstrap_household.py`
    does, so the two account-creation paths can never drift apart on what a
    valid username is.
    """
    username_field = User._meta.get_field('username')
    try:
        normalized = User.normalize_username(value)
        cleaned = username_field.clean(normalized, instance or User())
    except DjangoValidationError as error:
        raise serializers.ValidationError(error.messages) from error

    query = User.objects.filter(username=cleaned)
    if instance is not None and instance.pk is not None:
        query = query.exclude(pk=instance.pk)
    if query.exists():
        raise serializers.ValidationError([DUPLICATE_USERNAME_DETAIL])
    return cleaned


def _run_password_validators(value, candidate_user):
    try:
        validate_password(value, user=candidate_user)
    except DjangoValidationError as error:
        raise serializers.ValidationError(error.messages) from error


def _duplicate_username_error(error):
    """Turn a race that slipped past `_clean_username` into the same 400.

    Only `User.username` is unique among the columns this module ever
    inserts or updates, so any `IntegrityError` raised by the calls this
    wraps is that race, not a different fault.
    """
    return serializers.ValidationError({'username': [DUPLICATE_USERNAME_DETAIL]})


class MemberCreateSerializer(serializers.Serializer):
    """The only writable body a create may send: username, password, role."""

    username = serializers.CharField()
    password = serializers.CharField(trim_whitespace=False, write_only=True)
    role = serializers.ChoiceField(choices=Membership.Role.choices)

    def validate_username(self, value):
        return _clean_username(value)

    def validate_password(self, value):
        candidate = User(username=self.initial_data.get('username') or '')
        _run_password_validators(value, candidate)
        return value


class MemberUpdateSerializer(serializers.Serializer):
    """An edit body: username, password and role, each optional.

    A field left out of the request is left out of `validated_data`
    entirely, which is how the view tells "not sent" from "sent unchanged" -
    unlike `ChoreWriteSerializer`, this never runs under DRF's own `partial`
    flag, because every field is already declared optional here.
    """

    username = serializers.CharField(required=False)
    password = serializers.CharField(
        required=False, trim_whitespace=False, write_only=True
    )
    role = serializers.ChoiceField(required=False, choices=Membership.Role.choices)

    def validate_username(self, value):
        return _clean_username(value, instance=self.context['user'])

    def validate_password(self, value):
        _run_password_validators(value, self.context['user'])
        return value


def _member_payload(membership):
    """The exact five-key shape every route returns for one member.

    Built from `membership.user` and `membership.role` directly rather than
    through a `ModelSerializer`, because the role lives on `Membership` and
    the rest lives on `User` - there is no one model to bind a `ModelSerializer`
    to. Never a password, a hash, or a PIN.
    """
    user = membership.user
    return {
        'id': user.pk,
        'username': user.username,
        'role': membership.role,
        'is_active': user.is_active,
        'date_joined': user.date_joined,
    }


class _MemberAPIView(APIView):
    """Shared authority, scoping and audit behaviour for the member routes.

    An unsupported method is refused before authority is considered, so the
    answer to it never depends on who is asking and no handler can run for a
    method the route does not define.
    """

    renderer_classes = (JSONRenderer,)
    authentication_classes = (SessionAuthentication,)
    permission_classes = (IsHouseholdParent,)
    permission_household_attribute = 'household'

    def initial(self, request, *args, **kwargs):
        if request.method.lower() not in self.http_method_names:
            self.http_method_not_allowed(request)
        super().initial(request, *args, **kwargs)

    def get_permission_household(self, request):
        """The one household the caller may act in, or `None`."""
        membership = resolve_active_membership(request.user)
        return None if membership is None else membership.household

    def require_parent_membership(self):
        """Re-resolve the acting parent, for use inside a write transaction."""
        membership = resolve_active_membership(self.request.user)
        if membership is None or membership.role != Membership.Role.PARENT:
            raise PermissionDenied(PERMISSION_DENIED_DETAIL)
        return membership

    def get_member(self, pk):
        """Read one member of the caller's household, unlocked."""
        household = self.get_permission_household(self.request)
        membership = (
            Membership.objects.filter(household=household, user_id=pk)
            .select_related('user')
            .first()
        )
        if membership is None:
            raise NotFound()
        # The household of the stored row is checked a second time, so the
        # answer never rests on the query alone.
        self.check_object_permissions(self.request, membership)
        return membership

    def get_locked_member(self, household, pk):
        """Lock one member of `household` for a write, and the parent set.

        Returns `(membership, locked_parents)`. When the target is a parent,
        `_lock_parents` already holds their row, in the one fixed order every
        mutation uses; a child target is locked on its own, since a child can
        never be part of the last-active-parent count and so never needs to
        wait behind, or make anyone wait behind, the parent lock.
        """
        locked_parents = _lock_parents(household)
        membership = next((row for row in locked_parents if row.user_id == pk), None)
        if membership is None:
            membership = (
                Membership.objects.select_for_update()
                .filter(household=household, user_id=pk)
                .select_related('user')
                .first()
            )
        if membership is None:
            raise NotFound()
        self.check_object_permissions(self.request, membership)
        return membership, locked_parents

    def deny_self_action(self, actor, target):
        """Refuse to let the caller create, edit, deactivate or delete themselves.

        Non-enumerating on purpose: this is one more state the shared
        primitive's generic denial already covers, not a distinct reason a
        response should ever spell out.
        """
        if target.user_id == actor.user_id:
            raise PermissionDenied(PERMISSION_DENIED_DETAIL)

    def write_audit_event(self, actor, action, target_user_id, context):
        AuditEvent.objects.create(
            household=actor.household,
            actor=actor.user,
            action=action,
            target_type=AUDIT_TARGET_TYPE,
            target_id=str(target_user_id),
            context=context,
        )


class MemberListView(_MemberAPIView):
    """`GET /api/v1/household-members/` and `POST /api/v1/household-members/`."""

    http_method_names = ('get', 'head', 'post', 'options')

    def get(self, request):
        household = self.get_permission_household(request)
        members = Membership.objects.filter(household=household).select_related('user')

        include_inactive = (
            request.query_params.get(INCLUDE_INACTIVE_PARAMETER)
            == INCLUDE_INACTIVE_VALUE
        )
        if not include_inactive:
            members = members.filter(user__is_active=True)
        members = members.order_by('user__username', 'user_id')

        return Response([_member_payload(member) for member in members])

    def post(self, request):
        try:
            with transaction.atomic():
                actor = self.require_parent_membership()
                serializer = MemberCreateSerializer(data=request.data)
                serializer.is_valid(raise_exception=True)

                user = User.objects.create_user(
                    username=serializer.validated_data['username'],
                    password=serializer.validated_data['password'],
                )
                role = serializer.validated_data['role']
                member = Membership.objects.create(
                    household=actor.household, user=user, role=role
                )
                self.write_audit_event(
                    actor,
                    AUDIT_CREATE,
                    user.pk,
                    {
                        'actor_id': actor.user_id,
                        'target_id': user.pk,
                        'role': role,
                    },
                )
                body = _member_payload(member)
        except IntegrityError as error:
            raise _duplicate_username_error(error) from error
        return Response(body, status=status.HTTP_201_CREATED)


class MemberDetailView(_MemberAPIView):
    """`GET`, `PATCH` and `DELETE /api/v1/household-members/<pk>/`."""

    http_method_names = ('get', 'head', 'patch', 'delete', 'options')

    def get(self, request, pk):
        return Response(_member_payload(self.get_member(pk)))

    def patch(self, request, pk):
        try:
            with transaction.atomic():
                actor = self.require_parent_membership()
                target, locked_parents = self.get_locked_member(actor.household, pk)
                self.deny_self_action(actor, target)

                serializer = MemberUpdateSerializer(
                    data=request.data, context={'user': target.user}
                )
                serializer.is_valid(raise_exception=True)
                data = serializer.validated_data

                changes = {}
                user_fields = []

                if 'username' in data and data['username'] != target.user.username:
                    changes['username'] = {
                        'before': target.user.username,
                        'after': data['username'],
                    }
                    target.user.username = data['username']
                    user_fields.append('username')

                if 'password' in data:
                    target.user.set_password(data['password'])
                    changes['password'] = {'changed': True}
                    user_fields.append('password')

                role_changed = False
                if 'role' in data and data['role'] != target.role:
                    if (
                        target.role == Membership.Role.PARENT
                        and data['role'] != Membership.Role.PARENT
                    ):
                        _deny_if_would_remove_last_active_parent(
                            locked_parents, excluded_user_id=target.user_id
                        )
                    changes['role'] = {'before': target.role, 'after': data['role']}
                    target.role = data['role']
                    role_changed = True

                # An edit that changes nothing is not an edit: no write, and
                # no audit event.
                if changes:
                    if user_fields:
                        target.user.save(update_fields=user_fields)
                    if role_changed:
                        target.save(update_fields=('role',))
                    self.write_audit_event(
                        actor,
                        AUDIT_ROLE_CHANGE if role_changed else AUDIT_UPDATE,
                        target.user_id,
                        {
                            'actor_id': actor.user_id,
                            'target_id': target.user_id,
                            'changes': changes,
                        },
                    )
                body = _member_payload(target)
        except IntegrityError as error:
            raise _duplicate_username_error(error) from error
        return Response(body)

    def delete(self, request, pk):
        with transaction.atomic():
            actor = self.require_parent_membership()
            target, locked_parents = self.get_locked_member(actor.household, pk)
            self.deny_self_action(actor, target)

            if target.role == Membership.Role.PARENT:
                _deny_if_would_remove_last_active_parent(
                    locked_parents, excluded_user_id=target.user_id
                )

            user = target.user
            user_id = user.pk
            # Counts and identifiers only, per `_docs/retention-policy.md`:
            # the deletion event never records the removed member's username.
            # `rewards`, `progression` and `creatures` (T056, T062, T069) have
            # no user-linked table yet, so their counts are a constant zero
            # until one of those tasks adds a row to count here.
            context = {
                'actor_id': actor.user_id,
                'target_id': user_id,
                'role': target.role,
                'memberships_removed': 1,
                'submissions_removed': Submission.objects.filter(
                    child_id=user_id
                ).count(),
                'ledger_entries_removed': LedgerEntry.objects.filter(
                    user_id=user_id
                ).count(),
                'rewards_removed': 0,
                'progression_rows_removed': 0,
                'creature_selection_removed': 0,
            }
            user.delete()
            self.write_audit_event(actor, AUDIT_DELETE, user_id, context)
        return Response(status=status.HTTP_204_NO_CONTENT)


class _MemberStateView(_MemberAPIView):
    """One parent-only login-state transition, written exactly once."""

    http_method_names = ('post', 'options')
    target_state = None
    audit_action = None

    def post(self, request, pk):
        with transaction.atomic():
            actor = self.require_parent_membership()
            target, locked_parents = self.get_locked_member(actor.household, pk)
            self.deny_self_action(actor, target)

            # A member already in the target state is left alone: nothing is
            # written and no second event is recorded.
            if target.user.is_active != self.target_state:
                if self.target_state is False and target.role == Membership.Role.PARENT:
                    _deny_if_would_remove_last_active_parent(
                        locked_parents, excluded_user_id=target.user_id
                    )

                previous_state = target.user.is_active
                target.user.is_active = self.target_state
                target.user.save(update_fields=('is_active',))
                self.write_audit_event(
                    actor,
                    self.audit_action,
                    target.user_id,
                    {
                        'actor_id': actor.user_id,
                        'target_id': target.user_id,
                        'is_active': {
                            'before': previous_state,
                            'after': self.target_state,
                        },
                    },
                )
            body = _member_payload(target)
        return Response(body)


class MemberDeactivateView(_MemberStateView):
    """`POST /api/v1/household-members/<pk>/deactivate/`."""

    target_state = False
    audit_action = AUDIT_DEACTIVATE


class MemberReactivateView(_MemberStateView):
    """`POST /api/v1/household-members/<pk>/reactivate/`."""

    target_state = True
    audit_action = AUDIT_REACTIVATE
