"""Progression endpoints: the caller's own level, and its one write.

Two routes under `/api/v1/`, both same-origin session authenticated,
child-only, both scoped to the one household the caller is a live child of,
exactly as `api/balances.py` scopes its own two routes:

- `GET progression/` returns the caller's own level state: `level`,
  `max_level`, `lifetime_points`, `next_level_threshold`,
  `points_to_next_level`, and `pending_level_up`. Read-only; it writes
  nothing and emits no audit event, because computing a level is not an
  event any more than reading a balance is.
- `POST progression/acknowledge/` is the one write: it tells the server the
  caller has now seen their current level, so it is never shown again. There
  is no body, because there is nothing for a client to supply; the level
  being acknowledged is always the server's own freshly computed answer, per
  the permission matrix's "the client never supplies ... the resulting
  level". A repeat call, or a call with nothing newly reached, changes
  nothing and answers 200 with the same shape.

Authority is never taken from the client. The household comes from
`resolve_active_membership`, never from a body, query string, path or
header, so the answer is always the caller's own figures, and membership is
re-resolved inside the acknowledge write so a membership revoked a moment
ago cannot slip a write through.

Level: issue #61's decided policy. `chorum_murohc.progression.services` owns
the arithmetic and the write; this module owns only the HTTP shape.
"""

from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import PermissionDenied
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from chorum_murohc.api.permissions import PERMISSION_DENIED_DETAIL, IsHouseholdChild
from chorum_murohc.api.session import resolve_active_membership
from chorum_murohc.identity.models import Membership
from chorum_murohc.progression.services import (
    acknowledge_level_up,
    progression_summary_for_user,
)


class _ProgressionAPIView(APIView):
    """Shared authority for both progression routes.

    An unsupported method is refused before authority is considered, so the
    answer to an unlisted method never depends on who is asking.
    """

    renderer_classes = (JSONRenderer,)
    authentication_classes = (SessionAuthentication,)
    permission_classes = (IsHouseholdChild,)

    def initial(self, request, *args, **kwargs):
        if request.method.lower() not in self.http_method_names:
            self.http_method_not_allowed(request)
        super().initial(request, *args, **kwargs)

    def get_permission_household(self, request):
        """The one household the caller may read or act in, or `None`."""
        membership = resolve_active_membership(request.user, request)
        return None if membership is None else membership.household

    def require_child_membership(self):
        """Re-resolve the acting child, for use inside a write transaction."""
        membership = resolve_active_membership(self.request.user, self.request)
        if membership is None or membership.role != Membership.Role.CHILD:
            raise PermissionDenied(PERMISSION_DENIED_DETAIL)
        return membership


class ProgressionView(_ProgressionAPIView):
    """`GET /api/v1/progression/`: the caller's own level state."""

    http_method_names = ('get', 'head', 'options')

    def get(self, request):
        household = self.get_permission_household(request)
        return Response(progression_summary_for_user(household, request.user))


class ProgressionAcknowledgeView(_ProgressionAPIView):
    """`POST /api/v1/progression/acknowledge/`: mark the level as shown."""

    http_method_names = ('post', 'options')

    def post(self, request):
        membership = self.require_child_membership()
        summary, _changed = acknowledge_level_up(membership.household, membership.user)
        return Response(summary)
