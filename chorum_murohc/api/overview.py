"""The parent-only household overview: one bounded read-model composition.

One route: `GET /api/v1/overview/`. It answers the exact matrix row
`_docs/design.md` grants T084 ("Parent household overview... Allow minimum
own-household member, balance, level, and pending summary") and closes out
the three other rows that name T084 as their own summary contract: balance
and ledger history, level, and creature state.

This view creates no reporting model and no denormalised table. Every figure
is read fresh, at request time, straight from the tables `identity`,
`ledger`, `progression`'s own catalogue-driven math, `creatures`, and
`submissions` already own - exactly the tables their own dedicated endpoints
read, just composed into one household-shaped answer instead of one
member-shaped one.

Composing per member without an extra query per member matters here more
than it does on a single-user endpoint: a parent-scoped view can iterate
several children, so a helper called once per child (`balance_for_user`,
`progression_for_user`, `creature_state_for_user`) would turn one page load
into a query count that grows with the size of the household. Every figure
below is instead read as one query across the whole household - grouped by
user with the database's own aggregation - and matched back to each member in
Python, so the query count this view issues is fixed regardless of how many
children the household has. `test_overview.py`'s query-count tests prove
this directly, at more than one household size.

Level and creature state are still computed with the exact rules their own
packages own (`chorum_murohc.progression.services.level_for_lifetime_points`,
the catalogue's own form-unlock levels): this view supplies the aggregated
lifetime points and the stored line slug, never a second copy of the rule
that turns either into a level or a form.

The summary is deliberately minimal, per the matrix's "no detailed secret or
history expansion": a child's current balance, level and its ceiling, their
creature's line and current form by name only (not the full four-form
unlock list `GET /creature/` returns, and not the child's own note on a
pending submission), and a count of what is pending, never the submissions
themselves - a parent who wants to act on the queue already has `GET
/approvals/` for that.

Only active members are shown, matching `api/members.py`'s own default: a
deactivated account is already being managed on `/household`, and showing it
again here would be a second, easier-to-miss place the same fact lives.

Authority is never taken from the client. The household comes from
`resolve_active_membership`, exactly as every other endpoint in this package
derives it.
"""

from django.db.models import Count, Q, Sum
from rest_framework.authentication import SessionAuthentication
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from chorum_murohc.api.permissions import IsHouseholdParent
from chorum_murohc.api.session import resolve_active_membership
from chorum_murohc.creatures.catalogue import line_for_slug
from chorum_murohc.creatures.models import CreatureSelection
from chorum_murohc.identity.models import Membership
from chorum_murohc.ledger.models import LedgerEntry
from chorum_murohc.progression.models import MAX_LEVEL
from chorum_murohc.progression.services import level_for_lifetime_points
from chorum_murohc.submissions.models import Submission


def _points_totals(household):
    """`{user_id: (balance, lifetime_points)}` for the whole household.

    One query. `balance` sums every entry; `lifetime_points` sums only the
    positive ones, in the same aggregate rather than a second pass over the
    table, matching `progression.services.lifetime_points_earned_for_user`'s
    rule that a future debit reason is never netted against what was earned.
    A user with no entry at all has no row here; the caller supplies the
    `(0, 0)` default, exactly as the single-user service functions do.
    """
    rows = (
        LedgerEntry.objects.filter(household=household)
        .values('user_id')
        .annotate(
            balance=Sum('amount'),
            lifetime_points=Sum('amount', filter=Q(amount__gt=0)),
        )
    )
    return {
        row['user_id']: (row['balance'] or 0, row['lifetime_points'] or 0)
        for row in rows
    }


def _creature_slugs(household):
    """`{user_id: line_slug}` for the whole household. One query."""
    return dict(
        CreatureSelection.objects.filter(household=household).values_list(
            'user_id', 'line_slug'
        )
    )


def _pending_counts(household):
    """`{child_id: pending_count}` for the whole household. One query."""
    rows = (
        Submission.objects.filter(household=household, status=Submission.Status.PENDING)
        .values('child_id')
        .annotate(count=Count('id'))
    )
    return {row['child_id']: row['count'] for row in rows}


def _creature_summary(slug, level):
    """`(line_name, current_form_name)`, both `None` when unset or unearned.

    The catalogue is a Python constant (`chorum_murohc.creatures.catalogue`),
    so resolving a slug and walking its four forms costs no query; only the
    stored slug itself, already read in bulk above, comes from the database.
    """
    if slug is None:
        return None, None
    line = line_for_slug(slug)
    if line is None:
        # An unknown slug cannot be written today (the model's own check
        # constraint blocks it) but a summary must still answer something
        # for a row a future catalogue change orphaned, rather than 500.
        return None, None
    unlocked = [form for form in line.forms if form.unlock_level <= level]
    current_form = unlocked[-1].name if unlocked else None
    return line.name, current_form


def _child_summary(membership, points_totals, creature_slugs, pending_counts):
    balance, lifetime_points = points_totals.get(membership.user_id, (0, 0))
    level = level_for_lifetime_points(lifetime_points)
    line_name, current_form = _creature_summary(
        creature_slugs.get(membership.user_id), level
    )
    return {
        'id': membership.user_id,
        'username': membership.user.username,
        'balance': balance,
        'level': level,
        'max_level': MAX_LEVEL,
        'creature_line': line_name,
        'creature_form': current_form,
        'pending_count': pending_counts.get(membership.user_id, 0),
    }


def _parent_summary(membership):
    return {'id': membership.user_id, 'username': membership.user.username}


def household_overview(household):
    """The whole bounded summary for `household`. Four queries, always.

    One query for the member roster (`select_related` avoids a fifth for
    each member's username), and one grouped query each for points, creature
    selections and pending counts - never one per member, whatever the
    household's size.
    """
    members = list(
        Membership.objects.filter(household=household)
        .filter(user__is_active=True)
        .select_related('user')
        .order_by('user__username', 'user_id')
    )
    points_totals = _points_totals(household)
    creature_slugs = _creature_slugs(household)
    pending_counts = _pending_counts(household)

    children = [
        _child_summary(membership, points_totals, creature_slugs, pending_counts)
        for membership in members
        if membership.role == Membership.Role.CHILD
    ]
    parents = [
        _parent_summary(membership)
        for membership in members
        if membership.role == Membership.Role.PARENT
    ]

    return {
        'children': children,
        'parents': parents,
        'pending_total': sum(child['pending_count'] for child in children),
    }


class OverviewView(APIView):
    """`GET /api/v1/overview/`: the caller's own-household summary."""

    http_method_names = ('get', 'head', 'options')
    renderer_classes = (JSONRenderer,)
    authentication_classes = (SessionAuthentication,)
    permission_classes = (IsHouseholdParent,)

    def initial(self, request, *args, **kwargs):
        # An unsupported method is refused before authority is considered, so
        # the answer to `POST` never depends on who is asking.
        if request.method.lower() not in self.http_method_names:
            self.http_method_not_allowed(request)
        super().initial(request, *args, **kwargs)

    def get_permission_household(self, request):
        """The one household the caller may read, or `None`."""
        membership = resolve_active_membership(request.user)
        return None if membership is None else membership.household

    def get(self, request):
        household = self.get_permission_household(request)
        return Response(household_overview(household))
