"""Household-role permission primitive shared by every product endpoint.

This module implements the minimum reusable part of the approved authority
model recorded in the `Trust boundaries and permission matrix` section of
`_docs/design.md`. It reads only trusted server-side state: `request.user`
and `chorum_murohc.identity.models.Membership`. A body, query parameter,
path value, header, or any other client-supplied claim is never authority.

It holds no endpoint-specific policy. Every endpoint keeps its own row of
the permission matrix, supplies the household to check, and tests that row
itself.

Everything is fail-closed. No authenticated user, an inactive user, no
resolvable household, no membership, a stale or deleted membership, or an
unsupported role all deny. Denial is non-enumerating: one fixed generic
detail that names no household, user, role, or resource.
"""

from rest_framework.permissions import BasePermission

from chorum_murohc.identity.models import Household, Membership

# The one detail returned for every denial produced by this module, so that
# a foreign household is indistinguishable from a missing membership.
PERMISSION_DENIED_DETAIL = 'You do not have permission to perform this action.'


def resolve_membership(user, household):
    """Return the one live membership joining `user` to `household`.

    Return `None` for every state that must fail closed: no user, an
    unauthenticated user, an inactive user, an unsaved user, no household,
    a value that is not a saved `Household`, or no membership row.

    `is_authenticated`, `is_active`, and the membership row are read on every
    call, so a disabled account, a deleted membership, or a changed role takes
    effect on the very next request without any cache flush or restart.
    """
    if user is None or not user.is_authenticated or not user.is_active:
        return None
    if user.pk is None:
        return None
    if not isinstance(household, Household) or household.pk is None:
        return None
    try:
        # The `identity_membership_household_user_unique` constraint means the
        # pair matches at most one row, so this is an exact lookup and never
        # an unordered pick from several candidates.
        return Membership.objects.get(household=household, user=user)
    except Membership.DoesNotExist:
        return None


class _HouseholdRolePermission(BasePermission):
    """Allow only the one household role named by `required_role`.

    The view supplies the household to check and this primitive denies when
    it supplies none:

    - collection calls use `view.get_permission_household(request)`;
    - object calls read `view.permission_household_attribute` and take that
      attribute from the resource, so the household comes from the stored
      resource rather than from the client.
    """

    required_role = None
    message = PERMISSION_DENIED_DETAIL

    def has_permission(self, request, view):
        household_source = getattr(view, 'get_permission_household', None)
        if not callable(household_source):
            return False
        return self._has_required_role(request.user, household_source(request))

    def has_object_permission(self, request, view, obj):
        attribute = getattr(view, 'permission_household_attribute', None)
        if not attribute:
            return False
        return self._has_required_role(request.user, getattr(obj, attribute, None))

    def _has_required_role(self, user, household):
        membership = resolve_membership(user, household)
        # An unsupported or empty role matches neither required role, so it
        # denies. The `identity_membership_role_valid` constraint stops such a
        # row from being persisted; this comparison is the second line.
        return membership is not None and membership.role == self.required_role


class IsHouseholdParent(_HouseholdRolePermission):
    """Allow only a parent of the household the view supplies."""

    required_role = Membership.Role.PARENT


class IsHouseholdChild(_HouseholdRolePermission):
    """Allow only a child of the household the view supplies."""

    required_role = Membership.Role.CHILD
