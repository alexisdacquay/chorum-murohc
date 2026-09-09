"""The creature catalogue: seven lines, four forms each, fixed in code.

Issue #66 settled the rights question before a single shape was drawn: this
product uses no third-party intellectual property. Every line here is a
public-domain mythological archetype, and every image is an original flat SVG
drawn for this repository and committed to it. Nothing is downloaded at
runtime, nothing is fetched from an external image host, and no line is named
after, or drawn to resemble, anyone's character design.

The catalogue is a constant rather than a table because it is code, not
household data. It changes only when someone commits a new drawing, it is the
same for every household, and a loader command plus a migration to carry
seven rows nobody can edit would buy nothing. The one thing that IS household
data - which line a child picked - is the single row in `models.py`.

Ordering is the declaration order below, everywhere and always, so the chooser
shows the same seven lines in the same order to every child on every visit.

Assets live at `frontend/public/creatures/<slug>/form-<index>.svg` and are
served by the frontend at the path `asset_path` returns. That naming is
derived here rather than written out twenty-eight times, so a file can never
be referenced under a name it does not have; `test_catalogue.py` proves every
derived path resolves to a committed drawing.
"""

from dataclasses import dataclass

from chorum_murohc.progression.models import MAX_LEVEL

# The level at which form 1, 2, 3 and 4 unlock, in order. Four forms spread
# across the ten levels `chorum_murohc.progression` already owns: a child sees
# their creature change four times over the whole climb rather than nearly
# every level, which keeps each change worth waiting for. The thresholds
# themselves stay in `progression.services`; this tuple only says which level
# reveals which drawing.
FORM_UNLOCK_LEVELS = (1, 4, 7, 10)

FORMS_PER_LINE = len(FORM_UNLOCK_LEVELS)

# Where the drawings live in this repository, relative to the repository root.
ASSET_SOURCE_DIRECTORY = 'frontend/public/creatures'


@dataclass(frozen=True)
class CreatureForm:
    """One drawing in one line's evolution, and what unlocks it."""

    line_slug: str
    index: int
    name: str
    alt_text: str

    @property
    def unlock_level(self):
        return FORM_UNLOCK_LEVELS[self.index - 1]

    @property
    def asset_path(self):
        return f'/creatures/{self.line_slug}/form-{self.index}.svg'


@dataclass(frozen=True)
class CreatureLine:
    """One creature line and its four ordered forms."""

    slug: str
    name: str
    description: str
    forms: tuple


def _line(slug, name, description, forms):
    return CreatureLine(
        slug=slug,
        name=name,
        description=description,
        forms=tuple(
            CreatureForm(line_slug=slug, index=index, name=form_name, alt_text=alt_text)
            for index, (form_name, alt_text) in enumerate(forms, start=1)
        ),
    )


CREATURE_LINES = (
    _line(
        'dragon',
        'Dragon',
        'A scaled hoarder who grows wings, horns and a spiked tail.',
        (
            (
                'Hatchling',
                (
                    'A small green dragon hatchling sitting up, with stubby horns '
                    'and a short tail.'
                ),
            ),
            (
                'Fledgling',
                'A young green dragon with small folded wings and a pale belly.',
            ),
            (
                'Wyvern',
                (
                    'A large green dragon with wide open wings, curved horns and a '
                    'spade-tipped tail.'
                ),
            ),
            (
                'Elder Dragon',
                (
                    'A huge green dragon filling the frame, with spread wings, a '
                    'crest of spikes along its back and four horns.'
                ),
            ),
        ),
    ),
    _line(
        'golem',
        'Golem',
        'A figure of stone and clay, built square and built to last.',
        (
            (
                'Pebble',
                'A small round stone golem with two bright eyes and stubby feet.',
            ),
            (
                'Stone Golem',
                'A blocky grey stone golem with heavy arms and a flat brow.',
            ),
            (
                'Boulder Golem',
                'A large grey stone golem with shoulder plates and shards on its arms.',
            ),
            (
                'Mountain Golem',
                (
                    'A towering grey stone golem filling the frame, with a pale crystal '
                    'in its chest and shards across its shoulders.'
                ),
            ),
        ),
    ),
    _line(
        'griffin',
        'Griffin',
        'Half eagle and half lion, with an eye on every horizon.',
        (
            (
                'Gryphlet',
                'A small round golden griffin chick with a short curved beak.',
            ),
            (
                'Fledgling Griffin',
                'A young golden griffin with raised wings, a tufted tail and a hooked beak.',
            ),
            (
                'Sky Griffin',
                'A large golden griffin with wide open wings and a crest of feathers.',
            ),
            (
                'Storm Griffin',
                (
                    'A huge golden griffin filling the frame, with layered spread wings and '
                    'a tall feather crest.'
                ),
            ),
        ),
    ),
    _line(
        'phoenix',
        'Phoenix',
        'A bird of flame that begins again brighter every time.',
        (
            ('Ember', 'A small orange phoenix chick with a single flame on its head.'),
            (
                'Flame Bird',
                'A young orange phoenix with open wings and a trailing tail of flame.',
            ),
            (
                'Blazing Phoenix',
                'A large red and orange phoenix with wide wings and three long tail plumes.',
            ),
            (
                'Sun Phoenix',
                (
                    'A huge red and gold phoenix filling the frame, with layered wings, a '
                    'glowing breast and a fan of tail flames.'
                ),
            ),
        ),
    ),
    _line(
        'kraken',
        'Kraken',
        'A many-armed giant from the deepest, darkest water.',
        (
            (
                'Inkling',
                'A small teal kraken with a round head and three short tentacles.',
            ),
            (
                'Reef Lurker',
                'A young teal kraken with five tentacles and two small horns.',
            ),
            (
                'Deep Kraken',
                'A large teal kraken with six long curling tentacles and a spiked crown.',
            ),
            (
                'Abyssal Kraken',
                (
                    'A huge dark teal kraken filling the frame, with eight tentacles, a '
                    'spiked crown and a pale beak.'
                ),
            ),
        ),
    ),
    _line(
        'treant',
        'Treant',
        'A walking tree that carries a wider crown every season.',
        (
            (
                'Sapling',
                'A small smiling sapling with a slim trunk and a round green crown.',
            ),
            (
                'Young Treant',
                'A young treant with two branch arms and a broad green crown.',
            ),
            (
                'Elder Treant',
                'A large treant with four branch arms, a thick trunk and a spreading crown.',
            ),
            (
                'Ancient Treant',
                (
                    'A huge ancient treant filling the frame, with six branch arms, a hollow '
                    'in its trunk and a canopy of leaves.'
                ),
            ),
        ),
    ),
    _line(
        'sphinx',
        'Sphinx',
        'A winged guardian who answers questions only with riddles.',
        (
            (
                'Cub',
                'A small purple sphinx cub with a striped headdress and tufted ears.',
            ),
            (
                'Riddler',
                'A young purple sphinx with raised wings and a banded headdress.',
            ),
            (
                'Great Sphinx',
                'A large purple sphinx with wide wings, a layered headdress and a long tail.',
            ),
            (
                'Eternal Sphinx',
                (
                    'A huge purple sphinx filling the frame, with spread wings, a crowned '
                    'headdress and a pale gem on its chest.'
                ),
            ),
        ),
    ),
)

LINE_SLUGS = tuple(line.slug for line in CREATURE_LINES)

_LINES_BY_SLUG = {line.slug: line for line in CREATURE_LINES}

# The catalogue is a literal, so these hold at import time or not at all.
# They are asserts rather than tests because a broken catalogue must stop the
# process, not fail one test run: every other module here trusts these shapes.
assert len(LINE_SLUGS) == len(_LINES_BY_SLUG), 'creature line slugs must be unique'
assert all(len(line.forms) == FORMS_PER_LINE for line in CREATURE_LINES)
assert all(
    form.index == index
    for line in CREATURE_LINES
    for index, form in enumerate(line.forms, start=1)
)
assert list(FORM_UNLOCK_LEVELS) == sorted(set(FORM_UNLOCK_LEVELS))
assert FORM_UNLOCK_LEVELS[0] >= 1
assert FORM_UNLOCK_LEVELS[-1] <= MAX_LEVEL


def line_for_slug(slug):
    """The line with this slug, or `None`. Never raises on unknown input."""
    return _LINES_BY_SLUG.get(slug)
