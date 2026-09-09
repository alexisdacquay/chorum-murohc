"""Choosing a creature line, and resolving the forms a child has unlocked.

Two entry points:

- `creature_state_for_user` is a pure read: the caller's level, the line they
  picked (or `None` when they have not picked yet), and all four forms of that
  line with an `unlocked` flag on each. It never writes, and it never hides a
  locked form: the interface silhouettes what is still to come, which is only
  possible if the server says what is still to come.
- `select_creature_line` is the one write: it records the line a child picked
  and emits one `creature.line_selected` audit event. It is write-once. Asked
  again for the same line it changes nothing and emits nothing; asked for a
  different line it refuses, because a creature a child has been growing for
  weeks is not something a stray tap should be able to replace.

The level is never stored here and never supplied by a client. It is read
fresh from `chorum_murohc.progression`, which computes it from the ledger, so
unlocking a form needs no extra state to keep in step with anything.
"""

from django.db import transaction

from chorum_murohc.audit.models import AuditEvent
from chorum_murohc.creatures.catalogue import line_for_slug
from chorum_murohc.creatures.models import CreatureSelection
from chorum_murohc.progression.services import progression_for_user

AUDIT_TARGET_TYPE = 'creature'
AUDIT_LINE_SELECTED = 'creature.line_selected'


class UnknownCreatureLineError(ValueError):
    """The slug asked for is not in the catalogue."""


class CreatureLineAlreadyChosenError(RuntimeError):
    """A different line is already recorded for this child."""


def _form_state(form, level):
    return {
        'index': form.index,
        'name': form.name,
        'alt_text': form.alt_text,
        'unlock_level': form.unlock_level,
        'asset_path': form.asset_path,
        'unlocked': level >= form.unlock_level,
    }


def _line_state(line):
    return {'slug': line.slug, 'name': line.name, 'description': line.description}


def selected_line_slug(household, user):
    """The slug this child picked, or `None` when they have not picked yet."""
    return (
        CreatureSelection.objects.filter(household=household, user=user)
        .values_list('line_slug', flat=True)
        .first()
    )


def creature_state_for_user(household, user):
    """The caller's own creature: line, forms, and which are unlocked.

    With no selection yet, `line` and `current_form` are `None` and `forms` is
    empty: there is no line to show forms of, and picking one is the only
    thing the interface can offer.

    Below the first unlock level the line is set but `current_form` is `None`
    and every form reads locked. That is deliberate rather than a special
    case: the first form is a reward for the first level, and a child who has
    chosen sees four silhouettes and what each one costs.
    """
    state = progression_for_user(household, user)
    level = state['level']
    slug = selected_line_slug(household, user)
    line = None if slug is None else line_for_slug(slug)

    if line is None:
        return {
            'level': level,
            'max_level': state['max_level'],
            'line': None,
            'current_form': None,
            'forms': [],
        }

    forms = [_form_state(form, level) for form in line.forms]
    unlocked = [form for form in forms if form['unlocked']]

    return {
        'level': level,
        'max_level': state['max_level'],
        'line': _line_state(line),
        # The highest form reached, which is the last unlocked one because the
        # catalogue's unlock levels ascend.
        'current_form': unlocked[-1] if unlocked else None,
        'forms': forms,
    }


def select_creature_line(household, user, line_slug):
    """Record the line this child picked, exactly once.

    Returns `(state, created)`. `created` is true only for the call that wrote
    the row and the audit event; a repeat of the same choice returns false and
    writes nothing. A different choice raises
    `CreatureLineAlreadyChosenError` rather than overwriting.
    """
    line = line_for_slug(line_slug)
    if line is None:
        raise UnknownCreatureLineError(line_slug)

    with transaction.atomic():
        selection, created = (
            CreatureSelection.objects.select_for_update().get_or_create(
                household=household,
                user=user,
                defaults={'line_slug': line.slug},
            )
        )

        if not created and selection.line_slug != line.slug:
            raise CreatureLineAlreadyChosenError(selection.line_slug)

        if created:
            AuditEvent.objects.create(
                household=household,
                actor=user,
                action=AUDIT_LINE_SELECTED,
                target_type=AUDIT_TARGET_TYPE,
                target_id=str(selection.pk),
                context={'actor_id': user.pk, 'line_slug': line.slug},
            )

        return creature_state_for_user(household, user), created
