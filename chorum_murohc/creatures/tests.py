"""Tests for the `CreatureSelection` model and its database constraints.

Schema only: the catalogue is proved in `test_catalogue.py`, the selection and
unlock rules in `test_services.py`, and the HTTP shape in
`chorum_murohc/api/test_creatures.py`.

Every fixture is synthetic and no user is given a usable password, so nothing
sensitive appears in the data or in a failure message.
"""

import pytest
from django.db import IntegrityError, models, transaction
from django.db.models.deletion import ProtectedError

from chorum_murohc.creatures.catalogue import LINE_SLUGS
from chorum_murohc.creatures.models import LINE_SLUG_MAX_LENGTH, CreatureSelection
from chorum_murohc.identity.models import Household, Membership, User


def _household(name='Creature household'):
    return Household.objects.create(name=name)


def _child(household, username='child'):
    user = User.objects.create_user(username=username)
    Membership.objects.create(
        household=household, user=user, role=Membership.Role.CHILD
    )
    return user


def test_the_model_has_the_exact_runtime_contract():
    fields = CreatureSelection._meta.local_fields

    assert CreatureSelection.__bases__ == (models.Model,)
    assert tuple(field.name for field in fields) == (
        'id',
        'household',
        'user',
        'line_slug',
        'created_at',
    )

    _implicit_id, household, user, line_slug, created_at = fields
    assert household.remote_field.on_delete is models.PROTECT
    assert user.remote_field.on_delete is models.CASCADE
    assert line_slug.max_length == LINE_SLUG_MAX_LENGTH
    assert created_at.auto_now_add is True
    # Nothing is mutable after the row is written, so there is no updated_at
    # and no progress column: the forms unlocked are a function of the level.
    assert not any(field.name == 'updated_at' for field in fields)


@pytest.mark.django_db
def test_a_child_may_hold_only_one_selection_in_a_household():
    household = _household()
    child = _child(household)
    CreatureSelection.objects.create(
        household=household, user=child, line_slug='dragon'
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        CreatureSelection.objects.create(
            household=household, user=child, line_slug='golem'
        )


@pytest.mark.django_db
def test_the_database_refuses_a_line_the_catalogue_does_not_define():
    household = _household()
    child = _child(household)

    with pytest.raises(IntegrityError), transaction.atomic():
        CreatureSelection.objects.create(
            household=household, user=child, line_slug='stormtrooper'
        )


@pytest.mark.django_db
def test_the_database_accepts_every_line_the_catalogue_defines():
    household = _household()

    for index, slug in enumerate(LINE_SLUGS):
        child = _child(household, username=f'child-{index}')
        CreatureSelection.objects.create(
            household=household, user=child, line_slug=slug
        )

    assert CreatureSelection.objects.count() == len(LINE_SLUGS)


@pytest.mark.django_db
def test_deleting_a_child_removes_their_selection():
    household = _household()
    child = _child(household)
    CreatureSelection.objects.create(
        household=household, user=child, line_slug='sphinx'
    )

    child.delete()

    assert CreatureSelection.objects.count() == 0


@pytest.mark.django_db
def test_a_household_holding_a_selection_cannot_be_deleted():
    household = _household()
    child = _child(household)
    CreatureSelection.objects.create(
        household=household, user=child, line_slug='kraken'
    )

    with pytest.raises(ProtectedError):
        household.delete()
