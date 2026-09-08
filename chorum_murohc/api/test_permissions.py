"""Tests for the shared household-role permission primitive.

Every fixture here is synthetic: no credential, PIN, cookie, token, or
personal datum appears in the data, the assertions, or the failure output.
"""

import ast
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.contrib.auth.models import AnonymousUser
from django.contrib.sessions.backends.db import SessionStore
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory, force_authenticate
from rest_framework.views import APIView

from chorum_murohc.api import permissions
from chorum_murohc.api.permissions import (
    PERMISSION_DENIED_DETAIL,
    IsHouseholdChild,
    IsHouseholdParent,
    resolve_membership,
)
from chorum_murohc.audit.models import AuditEvent
from chorum_murohc.identity.models import Household, Membership, User

EXPECTED_PUBLIC_NAMES = frozenset(
    {
        # Imported building blocks.
        'BasePermission',
        'Household',
        'Membership',
        # The primitive itself.
        'PERMISSION_DENIED_DETAIL',
        'resolve_membership',
        'IsHouseholdParent',
        'IsHouseholdChild',
    }
)

DENIED_BODY = {'detail': PERMISSION_DENIED_DETAIL}
UNAUTHENTICATED_BODY = {'detail': 'Authentication credentials were not provided.'}
ALLOWED_BODY = {'allowed': True}

RESOURCE_ID = 4242
SENSITIVE_TEXT = (
    'synthetic',
    'parent',
    'child',
    'Household',
    'Membership',
    'Traceback',
)

factory = APIRequestFactory()


class _CollectionView(APIView):
    """Stand-in for a collection endpoint owned by a later task."""

    authentication_classes = (SessionAuthentication,)
    permission_classes = (IsHouseholdParent,)
    permission_household = None

    def get_permission_household(self, request):
        return self.permission_household

    def get(self, request):
        return Response(ALLOWED_BODY)


class _ObjectView(_CollectionView):
    """Stand-in for a detail endpoint that checks the resource household."""

    permission_household_attribute = 'household'
    resource = None

    def get(self, request):
        self.check_object_permissions(request, self.resource)
        return Response(ALLOWED_BODY)


class _UndeclaredHouseholdView(APIView):
    """A view that declares no household at all."""

    authentication_classes = (SessionAuthentication,)
    permission_classes = (IsHouseholdParent,)

    def get(self, request):
        return Response(ALLOWED_BODY)


def _resource(household):
    return SimpleNamespace(id=RESOURCE_ID, household=household)


def _call(view, user=None, path='/synthetic/resource/', **extra):
    request = factory.get(path, **extra)
    request.session = SessionStore()
    if user is not None:
        force_authenticate(request, user=user)
    response = view(request)
    response.render()
    response.wsgi_request = request
    return response


def _assert_allowed(response):
    assert response.status_code == 200
    assert json.loads(response.content) == ALLOWED_BODY


def _assert_non_enumerating(response, expected_body):
    assert response.status_code == 403
    assert json.loads(response.content) == expected_body

    body_text = response.content.decode()
    # No identifier of any kind can be in the body, so no digit may be either.
    assert not any(character.isdigit() for character in body_text)
    for text in SENSITIVE_TEXT:
        assert text not in body_text

    for header, value in response.headers.items():
        if header == 'Content-Length':
            continue
        for text in SENSITIVE_TEXT:
            assert text not in value


def _assert_denied(response):
    _assert_non_enumerating(response, DENIED_BODY)


@pytest.fixture
def household_a(db):
    return Household.objects.create(name='synthetic household a')


@pytest.fixture
def household_b(db):
    return Household.objects.create(name='synthetic household b')


@pytest.fixture
def parent_user(db):
    return User.objects.create(username='synthetic-parent-user')


@pytest.fixture
def child_user(db):
    return User.objects.create(username='synthetic-child-user')


def _membership(household, user, role):
    return Membership.objects.create(household=household, user=user, role=role)


# The module surface stays the primitive and nothing endpoint-specific.


def test_module_exposes_only_the_helper_and_the_two_role_classes():
    public_names = {name for name in vars(permissions) if not name.startswith('_')}

    assert public_names == set(EXPECTED_PUBLIC_NAMES)
    assert callable(resolve_membership)
    assert issubclass(IsHouseholdParent, BasePermission)
    assert issubclass(IsHouseholdChild, BasePermission)


def test_role_classes_require_exactly_one_role_and_share_one_denial_detail():
    assert IsHouseholdParent.required_role == Membership.Role.PARENT
    assert IsHouseholdChild.required_role == Membership.Role.CHILD
    assert IsHouseholdParent.message == PERMISSION_DENIED_DETAIL
    assert IsHouseholdChild.message == PERMISSION_DENIED_DETAIL


def test_module_imports_only_approved_modules_and_uses_no_dynamic_lookup():
    source = Path(permissions.__file__).read_text(encoding='utf-8')
    tree = ast.parse(source)

    imported_roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split('.')[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0
            module = node.module or ''
            if module.startswith('chorum_murohc'):
                assert module == 'chorum_murohc.identity.models'
            imported_roots.add(module.split('.')[0])

    assert imported_roots <= {'django', 'rest_framework', 'chorum_murohc'}
    for dodge in ('get_model', 'importlib', 'import_module', '__import__'):
        assert dodge not in source


# The resolution helper.


def test_resolution_returns_the_one_row_matched_on_household_and_user(
    household_a, household_b, parent_user, child_user
):
    rows = {
        (household_a.pk, parent_user.pk): _membership(
            household_a, parent_user, Membership.Role.PARENT
        ),
        (household_a.pk, child_user.pk): _membership(
            household_a, child_user, Membership.Role.CHILD
        ),
        (household_b.pk, parent_user.pk): _membership(
            household_b, parent_user, Membership.Role.CHILD
        ),
        (household_b.pk, child_user.pk): _membership(
            household_b, child_user, Membership.Role.PARENT
        ),
    }

    for (household_id, user_id), expected in rows.items():
        household = Household.objects.get(pk=household_id)
        user = User.objects.get(pk=user_id)

        # The unique constraint identity_membership_household_user_unique is
        # what makes this an exact lookup rather than a pick from a list.
        assert Membership.objects.filter(household=household, user=user).count() == 1
        resolved = resolve_membership(user, household)
        assert resolved is not None
        assert resolved.pk == expected.pk
        assert resolved.role == expected.role


def test_resolution_fails_closed_on_every_awkward_pair(
    household_a, household_b, parent_user
):
    _membership(household_a, parent_user, Membership.Role.PARENT)
    inactive_user = User.objects.create(username='synthetic-disabled', is_active=False)
    _membership(household_a, inactive_user, Membership.Role.PARENT)

    awkward_pairs = {
        'no user': (None, household_a),
        'anonymous user': (AnonymousUser(), household_a),
        'inactive user': (inactive_user, household_a),
        'unsaved user': (User(username='synthetic-unsaved'), household_a),
        'no household': (parent_user, None),
        'unsaved household': (parent_user, Household(name='synthetic unsaved')),
        'household primary key only': (parent_user, household_a.pk),
        'household name': (parent_user, household_a.name),
        'no membership row': (parent_user, household_b),
    }

    for label, (user, household) in awkward_pairs.items():
        assert resolve_membership(user, household) is None, label


# Allowed roles, on a collection call and on an object call.


def test_parent_in_own_household_is_allowed_on_collection_and_object_calls(
    household_a, parent_user
):
    _membership(household_a, parent_user, Membership.Role.PARENT)

    collection = _call(
        _CollectionView.as_view(permission_household=household_a), parent_user
    )
    detail = _call(
        _ObjectView.as_view(
            permission_household=household_a, resource=_resource(household_a)
        ),
        parent_user,
    )

    _assert_allowed(collection)
    _assert_allowed(detail)


def test_child_in_own_household_is_allowed_on_collection_and_object_calls(
    household_a, child_user
):
    _membership(household_a, child_user, Membership.Role.CHILD)

    collection = _call(
        _CollectionView.as_view(
            permission_classes=(IsHouseholdChild,), permission_household=household_a
        ),
        child_user,
    )
    detail = _call(
        _ObjectView.as_view(
            permission_classes=(IsHouseholdChild,),
            permission_household=household_a,
            resource=_resource(household_a),
        ),
        child_user,
    )

    _assert_allowed(collection)
    _assert_allowed(detail)


# Denied roles and denied states.


def test_denied_role_is_refused_in_both_directions(
    household_a, parent_user, child_user
):
    _membership(household_a, parent_user, Membership.Role.PARENT)
    _membership(household_a, child_user, Membership.Role.CHILD)

    child_on_parent_view = _call(
        _CollectionView.as_view(permission_household=household_a), child_user
    )
    parent_on_child_view = _call(
        _CollectionView.as_view(
            permission_classes=(IsHouseholdChild,), permission_household=household_a
        ),
        parent_user,
    )

    _assert_denied(child_on_parent_view)
    _assert_denied(parent_on_child_view)


def test_unauthenticated_request_is_denied_without_a_membership_query(household_a):
    view = _CollectionView.as_view(permission_household=household_a)

    with CaptureQueriesContext(connection) as queries:
        response = _call(view)

    assert queries.captured_queries == []
    _assert_non_enumerating(response, UNAUTHENTICATED_BODY)


def test_inactive_user_with_a_parent_membership_is_denied(household_a):
    inactive_parent = User.objects.create(
        username='synthetic-inactive-parent', is_active=False
    )
    _membership(household_a, inactive_parent, Membership.Role.PARENT)

    response = _call(
        _CollectionView.as_view(permission_household=household_a), inactive_parent
    )

    _assert_denied(response)


def test_missing_membership_and_cross_household_denials_are_byte_identical(
    household_a, household_b, parent_user
):
    _membership(household_a, parent_user, Membership.Role.PARENT)
    stranger = User.objects.create(username='synthetic-unaffiliated')

    missing_membership = _call(
        _CollectionView.as_view(permission_household=household_a), stranger
    )
    cross_household = _call(
        _CollectionView.as_view(permission_household=household_b), parent_user
    )

    _assert_denied(missing_membership)
    _assert_denied(cross_household)
    assert cross_household.status_code == missing_membership.status_code
    assert cross_household.content == missing_membership.content


def test_object_call_denies_a_resource_from_another_household(
    household_a, household_b, parent_user
):
    _membership(household_a, parent_user, Membership.Role.PARENT)

    response = _call(
        _ObjectView.as_view(
            permission_household=household_a, resource=_resource(household_b)
        ),
        parent_user,
    )

    _assert_denied(response)


def test_roles_never_union_across_households(household_a, household_b, parent_user):
    _membership(household_a, parent_user, Membership.Role.PARENT)
    _membership(household_b, parent_user, Membership.Role.CHILD)

    parent_check_in_b = _call(
        _CollectionView.as_view(permission_household=household_b), parent_user
    )
    child_check_in_a = _call(
        _CollectionView.as_view(
            permission_classes=(IsHouseholdChild,), permission_household=household_a
        ),
        parent_user,
    )

    _assert_denied(parent_check_in_b)
    _assert_denied(child_check_in_a)


def test_unknown_or_empty_role_is_denied(household_a, parent_user):
    # identity_membership_role_valid stops a row with an unsupported role from
    # ever being persisted, so the only way to reach this state is an unsaved
    # Membership handed back by the resolution helper.
    for unsupported_role in ('', 'guardian', 'PARENT', None):
        unsaved = Membership(
            household=household_a, user=parent_user, role=unsupported_role
        )
        assert unsaved.pk is None

        with patch.object(permissions, 'resolve_membership', return_value=unsaved):
            parent_response = _call(
                _CollectionView.as_view(permission_household=household_a), parent_user
            )
            child_response = _call(
                _CollectionView.as_view(
                    permission_classes=(IsHouseholdChild,),
                    permission_household=household_a,
                ),
                parent_user,
            )

        _assert_denied(parent_response)
        _assert_denied(child_response)


def test_deleted_membership_denies_the_very_next_request(household_a, parent_user):
    membership = _membership(household_a, parent_user, Membership.Role.PARENT)
    view = _CollectionView.as_view(permission_household=household_a)

    _assert_allowed(_call(view, parent_user))
    membership.delete()

    _assert_denied(_call(view, parent_user))


def test_changed_role_is_reflected_on_the_very_next_request(household_a, parent_user):
    membership = _membership(household_a, parent_user, Membership.Role.PARENT)
    parent_view = _CollectionView.as_view(permission_household=household_a)
    child_view = _CollectionView.as_view(
        permission_classes=(IsHouseholdChild,), permission_household=household_a
    )

    _assert_allowed(_call(parent_view, parent_user))
    _assert_denied(_call(child_view, parent_user))

    membership.role = Membership.Role.CHILD
    membership.save(update_fields=['role'])

    _assert_denied(_call(parent_view, parent_user))
    _assert_allowed(_call(child_view, parent_user))


def test_a_disabled_account_denies_the_very_next_request(household_a, parent_user):
    _membership(household_a, parent_user, Membership.Role.PARENT)
    view = _CollectionView.as_view(permission_household=household_a)

    _assert_allowed(_call(view, parent_user))
    parent_user.is_active = False
    parent_user.save(update_fields=['is_active'])

    _assert_denied(_call(view, parent_user))


def test_an_unresolvable_household_is_denied_and_never_defaulted(
    household_a, parent_user
):
    _membership(household_a, parent_user, Membership.Role.PARENT)

    no_declaration = _call(_UndeclaredHouseholdView.as_view(), parent_user)
    household_is_none = _call(
        _CollectionView.as_view(permission_household=None), parent_user
    )
    object_attribute_absent = _call(
        _ObjectView.as_view(
            permission_household=household_a,
            permission_household_attribute=None,
            resource=_resource(household_a),
        ),
        parent_user,
    )
    object_household_is_none = _call(
        _ObjectView.as_view(permission_household=household_a, resource=_resource(None)),
        parent_user,
    )

    _assert_denied(no_declaration)
    _assert_denied(household_is_none)
    _assert_denied(object_attribute_absent)
    _assert_denied(object_household_is_none)


def test_platform_flags_grant_no_household_authority(household_a, household_b):
    platform_admin = User.objects.create(
        username='synthetic-platform-admin', is_staff=True, is_superuser=True
    )
    parent_view = _CollectionView.as_view(permission_household=household_a)

    without_membership = _call(parent_view, platform_admin)

    _membership(household_a, platform_admin, Membership.Role.CHILD)
    with_child_membership = _call(parent_view, platform_admin)
    in_another_household = _call(
        _CollectionView.as_view(permission_household=household_b), platform_admin
    )

    _assert_denied(without_membership)
    _assert_denied(with_child_membership)
    _assert_denied(in_another_household)


def test_client_supplied_household_and_role_change_no_outcome(
    household_a, household_b, parent_user, child_user
):
    _membership(household_a, parent_user, Membership.Role.PARENT)
    _membership(household_a, child_user, Membership.Role.CHILD)
    forged_path = f'/synthetic/households/{household_a.pk}/resources/{RESOURCE_ID}/'
    forged_query = {
        'household': str(household_a.pk),
        'role': Membership.Role.PARENT.value,
    }
    forged_headers = {
        'HTTP_X_HOUSEHOLD': str(household_a.pk),
        'HTTP_X_ROLE': Membership.Role.PARENT.value,
    }

    # The view resolves household B server-side; the client claims household A.
    parent_forging_a_household = _call(
        _CollectionView.as_view(permission_household=household_b),
        parent_user,
        path=forged_path,
        data=forged_query,
        **forged_headers,
    )
    # A child claiming the parent role stays a child.
    child_forging_a_role = _call(
        _CollectionView.as_view(permission_household=household_a),
        child_user,
        path=forged_path,
        data=forged_query,
        **forged_headers,
    )
    # A forged claim does not disturb a genuinely permitted request either.
    parent_with_forged_claims = _call(
        _ObjectView.as_view(
            permission_household=household_a, resource=_resource(household_a)
        ),
        parent_user,
        path=forged_path,
        data=forged_query,
        **forged_headers,
    )

    _assert_denied(parent_forging_a_household)
    _assert_denied(child_forging_a_role)
    _assert_allowed(parent_with_forged_claims)


def test_permitted_and_denied_calls_write_nothing_and_touch_no_session(
    household_a, household_b, parent_user
):
    _membership(household_a, parent_user, Membership.Role.PARENT)
    permitted_view = _ObjectView.as_view(
        permission_household=household_a, resource=_resource(household_a)
    )
    denied_view = _CollectionView.as_view(permission_household=household_b)
    counts_before = (
        User.objects.count(),
        Household.objects.count(),
        Membership.objects.count(),
        AuditEvent.objects.count(),
    )

    for view in (permitted_view, denied_view):
        with CaptureQueriesContext(connection) as queries:
            response = _call(view, parent_user)

        statements = [entry['sql'] for entry in queries.captured_queries]
        assert statements
        for statement in statements:
            assert statement.lstrip().upper().startswith('SELECT')
        assert response.wsgi_request.session.accessed is False
        assert response.wsgi_request.session.modified is False
        assert response.wsgi_request.session.session_key is None

    assert counts_before == (
        User.objects.count(),
        Household.objects.count(),
        Membership.objects.count(),
        AuditEvent.objects.count(),
    )
