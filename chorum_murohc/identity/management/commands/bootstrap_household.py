import getpass
import os

from django.contrib.auth.hashers import check_password
from django.contrib.auth.password_validation import validate_password
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from chorum_murohc.audit.models import AuditEvent
from chorum_murohc.identity.models import Household, Membership, User

_ENVIRONMENT_KEYS = (
    'CHORUM_BOOTSTRAP_HOUSEHOLD_NAME',
    'CHORUM_BOOTSTRAP_USERNAME',
    'CHORUM_BOOTSTRAP_PASSWORD',
)
_HOUSEHOLD_ACTION = 'bootstrap.household.created'
_PARENT_ACTION = 'bootstrap.parent.created'
_ERROR = 'Bootstrap could not be completed.'
_SUCCESS = 'Bootstrap completed.'
_NO_CHANGE = 'Bootstrap already completed; no changes made.'


def _reject():
    raise CommandError(_ERROR)


def _read_environment_inputs():
    values = tuple(os.environ.get(key) for key in _ENVIRONMENT_KEYS)
    if any(value is None or value == '' for value in values):
        _reject()
    return values


def _read_interactive_inputs():
    household_name = input('Household name: ')
    username = input('Parent username: ')
    password = getpass.getpass('Password: ')
    confirmation = getpass.getpass('Confirm password: ')
    if password != confirmation:
        _reject()
    return household_name, username, password


def _validate_inputs(household_name, username, password):
    if (
        not household_name
        or household_name != household_name.strip()
        or not username
        or username != username.strip()
    ):
        _reject()

    normalized_username = User.normalize_username(username)
    household_field = Household._meta.get_field('name')
    username_field = User._meta.get_field(User.USERNAME_FIELD)
    candidate_user = User(username=normalized_username)
    try:
        household_name = household_field.clean(
            household_name,
            Household(),
        )
        normalized_username = username_field.clean(
            normalized_username,
            candidate_user,
        )
        candidate_user.username = normalized_username
        validate_password(password, user=candidate_user)
    except ValidationError:
        _reject()
    return household_name, normalized_username, password


def _acquire_serialisation_lock():
    ContentType.objects.select_for_update().only('pk').get(
        app_label='identity',
        model='user',
    )


def _product_state_is_empty():
    return not any(
        model.objects.exists() for model in (User, Household, Membership, AuditEvent)
    )


def _completed_bootstrap_matches(household_name, username, password):
    markers = list(
        AuditEvent.objects.filter(action__startswith='bootstrap.').select_related(
            'household'
        )
    )
    if len(markers) != 2:
        return False
    markers_by_action = {marker.action: marker for marker in markers}
    if set(markers_by_action) != {_HOUSEHOLD_ACTION, _PARENT_ACTION}:
        return False

    household_marker = markers_by_action[_HOUSEHOLD_ACTION]
    parent_marker = markers_by_action[_PARENT_ACTION]
    if (
        household_marker.actor_id is not None
        or household_marker.target_type != 'identity.Household'
        or household_marker.target_id != str(household_marker.household_id)
        or household_marker.context != {}
        or parent_marker.actor_id is not None
        or parent_marker.household_id != household_marker.household_id
        or parent_marker.target_type != 'identity.User'
        or parent_marker.context != {'role': Membership.Role.PARENT.value}
    ):
        return False

    household = household_marker.household
    user = User.objects.filter(username=username).first()
    if (
        user is None
        or household.name != household_name
        or parent_marker.target_id != str(user.pk)
        or not user.is_active
        or user.is_staff
        or user.is_superuser
        or not check_password(password, user.password)
    ):
        return False

    return (
        Membership.objects.filter(
            household=household,
            user=user,
            role=Membership.Role.PARENT,
        ).count()
        == 1
    )


def _create_bootstrap(household_name, username, password):
    user = User.objects.create_user(username=username, password=password)
    household = Household.objects.create(name=household_name)
    Membership.objects.create(
        household=household,
        user=user,
        role=Membership.Role.PARENT,
    )
    AuditEvent.objects.create(
        household=household,
        actor=None,
        action=_HOUSEHOLD_ACTION,
        target_type='identity.Household',
        target_id=str(household.pk),
        context={},
    )
    AuditEvent.objects.create(
        household=household,
        actor=None,
        action=_PARENT_ACTION,
        target_type='identity.User',
        target_id=str(user.pk),
        context={'role': Membership.Role.PARENT.value},
    )


class Command(BaseCommand):
    help = 'Create the first household and parent account.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--no-input',
            action='store_true',
            help='Read required bootstrap values from the process environment.',
        )

    def handle(self, *args, **options):
        try:
            raw_inputs = (
                _read_environment_inputs()
                if options['no_input']
                else _read_interactive_inputs()
            )
            household_name, username, password = _validate_inputs(*raw_inputs)
        except CommandError:
            raise
        except Exception:  # noqa: BLE001 - command output must stay generic.
            raise CommandError(_ERROR) from None

        try:
            with transaction.atomic():
                _acquire_serialisation_lock()
                if _product_state_is_empty():
                    _create_bootstrap(household_name, username, password)
                    created = True
                elif _completed_bootstrap_matches(
                    household_name,
                    username,
                    password,
                ):
                    created = False
                else:
                    _reject()
        except CommandError:
            raise
        except Exception:  # noqa: BLE001 - rollback and generic failure are required.
            raise CommandError(_ERROR) from None

        self.stdout.write(_SUCCESS if created else _NO_CHANGE)
