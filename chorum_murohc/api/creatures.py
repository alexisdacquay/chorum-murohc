"""Creature endpoints: the catalogue to pick from, and the caller's own creature.

Two routes under `/api/v1/`, same-origin session authenticated and child-only,
scoped exactly as `api/progression.py` scopes its own pair:

- `GET creature/lines/` returns the seven lines a child may pick from, in
  catalogue order, each with the drawing shown in the chooser. It is a
  constant, but it stays an endpoint rather than a build-time copy in the
  interface so the drawings and their alternative text have one owner.
- `GET creature/` returns the caller's own creature: their level, the line
  they picked (or `null`), the form they are on, and all four forms with an
  `unlocked` flag, so the interface can silhouette what is still to come.
- `POST creature/` records the line the caller picked. First sign-in only in
  practice, but the server does not depend on that: it is write-once, so the
  first call answers 201, a repeat of the same line answers 200 and changes
  nothing, and a different line answers 409.

A parent is denied here, including for their own children. The permission
matrix gives the parent side only the plan-required household summary and
routes it elsewhere, so a parent-visible route added here would widen a matrix
this feature has not been approved to widen.

Authority is never taken from the client. The household comes from
`resolve_active_membership`, never from a body, query string, path or header,
and membership is re-resolved inside the write so a membership revoked a
moment ago cannot slip a selection through. The client supplies one thing
only, the slug it picked; the level, the forms and the unlock rules are all
the server's own answer.
"""

from rest_framework import serializers, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import APIException, PermissionDenied
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from chorum_murohc.api.permissions import PERMISSION_DENIED_DETAIL, IsHouseholdChild
from chorum_murohc.api.session import resolve_active_membership
from chorum_murohc.creatures.catalogue import CREATURE_LINES, LINE_SLUGS
from chorum_murohc.creatures.services import (
    CreatureLineAlreadyChosenError,
    UnknownCreatureLineError,
    creature_state_for_user,
    select_creature_line,
)
from chorum_murohc.identity.models import Membership

# The one detail returned when a child who already has a creature asks for a
# different one. It names neither line: the interface reloads and shows the
# creature the server actually holds.
LINE_ALREADY_CHOSEN_DETAIL = 'A creature has already been chosen for this account.'


class CreatureLineAlreadyChosen(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = LINE_ALREADY_CHOSEN_DETAIL
    default_code = 'creature_line_already_chosen'


class CreatureSelectionSerializer(serializers.Serializer):
    """The only writable body: which line, by slug.

    A `ChoiceField` over the catalogue, so an unknown or retired slug is a 400
    naming the field rather than anything the service has to interpret.
    """

    line = serializers.ChoiceField(choices=LINE_SLUGS)


def _chooser_form(form):
    """The one drawing the chooser shows for a line."""
    return {
        'index': form.index,
        'name': form.name,
        'alt_text': form.alt_text,
        'unlock_level': form.unlock_level,
        'asset_path': form.asset_path,
    }


def catalogue_body():
    """The seven lines a child picks from, in catalogue order."""
    return {
        'lines': [
            {
                'slug': line.slug,
                'name': line.name,
                'description': line.description,
                'preview': _chooser_form(line.forms[0]),
            }
            for line in CREATURE_LINES
        ]
    }


class _CreatureAPIView(APIView):
    """Shared authority for both creature routes.

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
        """Re-resolve the acting child, for use inside a write."""
        membership = resolve_active_membership(self.request.user, self.request)
        if membership is None or membership.role != Membership.Role.CHILD:
            raise PermissionDenied(PERMISSION_DENIED_DETAIL)
        return membership


class CreatureLineListView(_CreatureAPIView):
    """`GET /api/v1/creature/lines/`: the lines a child may pick from."""

    http_method_names = ('get', 'head', 'options')

    def get(self, request):
        return Response(catalogue_body())


class CreatureView(_CreatureAPIView):
    """`GET` and `POST /api/v1/creature/`: read, then pick once."""

    http_method_names = ('get', 'head', 'post', 'options')

    def get(self, request):
        household = self.get_permission_household(request)
        return Response(creature_state_for_user(household, request.user))

    def post(self, request):
        membership = self.require_child_membership()
        serializer = CreatureSelectionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            state, created = select_creature_line(
                membership.household,
                membership.user,
                serializer.validated_data['line'],
            )
        except CreatureLineAlreadyChosenError:
            raise CreatureLineAlreadyChosen() from None
        except UnknownCreatureLineError:
            # Unreachable through the serializer above; kept so the service's
            # own guard cannot turn into a 500 if the two ever disagree.
            raise serializers.ValidationError(
                {'line': ['Select a valid creature.']}
            ) from None

        response_status = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(state, status=response_status)
