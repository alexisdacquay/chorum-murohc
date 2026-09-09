"""Isolated household data for one browser-journey run.

Every run of the harness mints one run token. The token names the SQLite
file the run uses, and it is the suffix of every household name and every
username the run creates; every password and every PIN is freshly generated
from `secrets` for that run alone. Two runs therefore cannot share a
database, a household, a user or a credential, whether they run one after
the other or at the same time, and neither can two journeys inside one run:
each journey gets its own household.

The data is created through the product's own models and services, not
through fixtures of a private shape, so a journey drives the same rows the
application would have written itself.

Nothing here is imported by product code.
"""

import secrets

from django.contrib.auth import get_user_model

from chorum_murohc.chores.models import Chore
from chorum_murohc.creatures.models import CreatureSelection
from chorum_murohc.identity.models import Household, Membership
from chorum_murohc.identity.services import PinWeakError, set_or_replace_pin
from chorum_murohc.ledger.models import LedgerEntry
from chorum_murohc.rewards.models import Reward
from chorum_murohc.submissions.models import Submission

# One household per journey, so a journey cannot see or disturb another
# journey's rows even though they share one throwaway database.
JOURNEY_NAMES = (
    'smoke',
    'child-submission',
    'parent-queue',
    'reward',
    'creature',
    'audit-accessibility',
    'audit-security',
)

TOKEN_BYTES = 5
PIN_DIGITS = 6


def new_run_token():
    """A fresh lowercase hex token that names one run and everything in it."""
    return secrets.token_hex(TOKEN_BYTES)


def _password():
    return f'journey-{secrets.token_urlsafe(12)}'


def _pin():
    """A random PIN the product's own weak-PIN rules accept."""
    return ''.join(secrets.choice('0123456789') for _ in range(PIN_DIGITS))


def _member(household, token, journey, role, label):
    """Create one user, their membership, and return them with the password."""
    user_model = get_user_model()
    password = _password()
    user = user_model.objects.create_user(
        username=f'{journey}-{label}-{token}',
        password=password,
    )
    Membership.objects.create(household=household, user=user, role=role)
    return user, {'username': user.username, 'password': password}


def _parent_with_pin(household, token, journey, label):
    user, credentials = _member(
        household,
        token,
        journey,
        Membership.Role.PARENT,
        label,
    )
    while True:
        pin = _pin()
        try:
            set_or_replace_pin(
                user=user,
                household=household,
                current_password=credentials['password'],
                new_pin=pin,
            )
        except PinWeakError:
            # A random six-digit value is occasionally a run or a repeated
            # pattern. Draw again rather than weaken the product's own rule.
            continue
        credentials['pin'] = pin
        return user, credentials


def _household(token, journey):
    return Household.objects.create(name=f'{journey} household {token}')


def _credit(household, user, amount, key):
    """One earned-points ledger entry, the only way a balance grows here."""
    LedgerEntry.objects.create(
        household=household,
        user=user,
        amount=amount,
        reason=LedgerEntry.Reason.CHORE_CREDIT,
        source_type='browser_journeys.seed',
        source_id=key,
        idempotency_key=f'seed-{key}',
    )


def _pending_submission(household, child, chore, key, note=''):
    return Submission.objects.create(
        household=household,
        child=child,
        chore=chore,
        chore_name=chore.name,
        chore_points=chore.points,
        note=note,
        idempotency_key=f'seed-{key}',
    )


def _seed_smoke(token):
    """The non-product smoke dataset: one household and one parent."""
    household = _household(token, 'smoke')
    _, parent = _parent_with_pin(household, token, 'smoke', 'parent')
    return {'household': household.name, 'parent': parent}


def _seed_child_submission(token):
    """A child with two chores, and two parents who each hold their own PIN.

    Two parents, because the child-device flow names the approving parent
    first and "a PIN that would have matched another parent fails": the
    journey proves that by offering the second parent's PIN against the
    first.
    """
    journey = 'child-submission'
    household = _household(token, journey)
    _, parent_one = _parent_with_pin(household, token, journey, 'parent-one')
    _, parent_two = _parent_with_pin(household, token, journey, 'parent-two')
    child_user, child = _member(
        household,
        token,
        journey,
        Membership.Role.CHILD,
        'child',
    )
    approved = Chore.objects.create(
        household=household,
        name='Tidy the bedroom',
        points=60,
    )
    rejected = Chore.objects.create(
        household=household,
        name='Empty the dishwasher',
        points=25,
    )
    return {
        'household': household.name,
        'parentOne': parent_one,
        'parentTwo': parent_two,
        'child': child,
        'choreToApprove': {'name': approved.name, 'points': approved.points},
        'choreToReject': {'name': rejected.name, 'points': rejected.points},
        'startingBalance': 0,
        'childId': child_user.pk,
    }


def _seed_parent_queue(token):
    """Two submissions already waiting, created without touching the browser.

    T090 asks that the parent-queue journey not repeat the child-submission
    setup through the interface, so the pending work is seeded directly.
    """
    journey = 'parent-queue'
    household = _household(token, journey)
    _, parent = _parent_with_pin(household, token, journey, 'parent')
    child_user, child = _member(
        household,
        token,
        journey,
        Membership.Role.CHILD,
        'child',
    )
    to_approve = Chore.objects.create(
        household=household,
        name='Walk the dog',
        points=30,
    )
    to_reject = Chore.objects.create(
        household=household,
        name='Rake the leaves',
        points=15,
    )
    _pending_submission(household, child_user, to_approve, 'queue-approve')
    _pending_submission(household, child_user, to_reject, 'queue-reject')
    return {
        'household': household.name,
        'parent': parent,
        'child': child,
        'choreToApprove': {'name': to_approve.name, 'points': to_approve.points},
        'choreToReject': {'name': to_reject.name, 'points': to_reject.points},
    }


def _seed_reward(token):
    """A child holding points, one reward they can afford and one they cannot."""
    journey = 'reward'
    household = _household(token, journey)
    _parent_with_pin(household, token, journey, 'parent')
    child_user, child = _member(
        household,
        token,
        journey,
        Membership.Role.CHILD,
        'child',
    )
    balance = 120
    _credit(household, child_user, balance, f'reward-{token}')
    affordable = Reward.objects.create(
        household=household,
        name='Movie night',
        points=40,
    )
    unaffordable = Reward.objects.create(
        household=household,
        name='New bicycle',
        points=5000,
    )
    return {
        'household': household.name,
        'child': child,
        'startingBalance': balance,
        'affordableReward': {
            'name': affordable.name,
            'points': affordable.points,
        },
        'unaffordableReward': {
            'name': unaffordable.name,
            'points': unaffordable.points,
        },
    }


def _seed_creature(token):
    """One child who has never chosen, and one who has already levelled.

    The chooser child proves onboarding; the levelled child proves evolution.
    A creature cannot be earned into a new form from inside one browser
    session, so the two halves are two children rather than one long wait.
    """
    journey = 'creature'
    household = _household(token, journey)
    _parent_with_pin(household, token, journey, 'parent')
    _, chooser = _member(
        household,
        token,
        journey,
        Membership.Role.CHILD,
        'chooser',
    )
    evolved_user, evolved = _member(
        household,
        token,
        journey,
        Membership.Role.CHILD,
        'evolved',
    )
    # 60 lifetime points clears the level-1 threshold of 50, which is the
    # level that reveals the first creature form.
    lifetime_points = 60
    _credit(household, evolved_user, lifetime_points, f'creature-{token}')
    CreatureSelection.objects.create(
        household=household,
        user=evolved_user,
        line_slug='phoenix',
    )
    return {
        'household': household.name,
        'chooser': chooser,
        'evolved': evolved,
        'evolvedLine': 'phoenix',
        'evolvedLevel': 1,
        'evolvedLifetimePoints': lifetime_points,
    }


def _seed_audit_accessibility(token):
    """One household with something on every screen the audit has to visit.

    An empty screen hides most of what an accessibility audit is looking for,
    so this household has a chore, a reward, points, a level, a creature and
    a submission waiting for a decision.
    """
    journey = 'audit-accessibility'
    household = _household(token, journey)
    _, parent = _parent_with_pin(household, token, journey, 'parent')
    child_user, child = _member(
        household,
        token,
        journey,
        Membership.Role.CHILD,
        'child',
    )
    chore = Chore.objects.create(
        household=household,
        name='Load the dishwasher',
        points=20,
    )
    Chore.objects.create(household=household, name='Sweep the hall', points=10)
    Reward.objects.create(household=household, name='Extra story', points=30)
    lifetime_points = 80
    _credit(household, child_user, lifetime_points, f'audit-{token}')
    CreatureSelection.objects.create(
        household=household,
        user=child_user,
        line_slug='griffin',
    )
    _pending_submission(household, child_user, chore, 'audit-pending')
    return {
        'household': household.name,
        'parent': parent,
        'child': child,
        'startingBalance': lifetime_points,
    }


def _seed_audit_security(token):
    """A child and a parent in one household, for live authority probes."""
    journey = 'audit-security'
    household = _household(token, journey)
    _, parent = _parent_with_pin(household, token, journey, 'parent')
    _, child = _member(household, token, journey, Membership.Role.CHILD, 'child')
    Chore.objects.create(household=household, name='Fold the washing', points=10)
    return {'household': household.name, 'parent': parent, 'child': child}


_SEEDERS = {
    'smoke': _seed_smoke,
    'child-submission': _seed_child_submission,
    'parent-queue': _seed_parent_queue,
    'reward': _seed_reward,
    'creature': _seed_creature,
    'audit-accessibility': _seed_audit_accessibility,
    'audit-security': _seed_audit_security,
}


def seed_dataset(token):
    """Create every journey's household and return the run's dataset."""
    return {
        'token': token,
        'journeys': {name: _SEEDERS[name](token) for name in JOURNEY_NAMES},
    }
