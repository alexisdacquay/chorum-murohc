"""Tests for the creature catalogue and the drawings it points at.

The catalogue is a constant, so most of what could go wrong is a file that is
missing, misnamed, empty, or drawn to a different size from the other
twenty-seven. Those are exactly the failures nobody notices in a code review
and everybody notices on the screen, so they are checked here against the
committed files rather than against a fixture.

No network, no image library and no rasteriser: the drawings are plain SVG
text, so the checks read them as text.
"""

import re
from pathlib import Path
from xml.etree import ElementTree

from django.conf import settings

from chorum_murohc.creatures.catalogue import (
    ASSET_SOURCE_DIRECTORY,
    CREATURE_LINES,
    FORM_UNLOCK_LEVELS,
    FORMS_PER_LINE,
    LINE_SLUGS,
    line_for_slug,
)
from chorum_murohc.progression.models import MAX_LEVEL

EXPECTED_LINE_COUNT = 7

# Every drawing shares one square canvas, so a form never jumps size mid-line
# and the chooser's seven previews line up.
EXPECTED_VIEW_BOX = '0 0 96 96'

# Comfortably above any of the drawings and far below anything that would slow
# a phone down. The largest today is under 2 kB.
MAX_ASSET_BYTES = 8192

SVG_NAMESPACE = '{http://www.w3.org/2000/svg}svg'
SVG_NAMESPACE_DECLARATION = 'xmlns="http://www.w3.org/2000/svg"'

ASSET_ROOT = Path(settings.BASE_DIR) / ASSET_SOURCE_DIRECTORY


def all_forms():
    return [(line, form) for line in CREATURE_LINES for form in line.forms]


def asset_file(form):
    return ASSET_ROOT / form.asset_path.removeprefix('/creatures/')


def test_the_catalogue_holds_seven_lines_in_a_stable_order():
    assert len(CREATURE_LINES) == EXPECTED_LINE_COUNT
    assert LINE_SLUGS == (
        'dragon',
        'golem',
        'griffin',
        'phoenix',
        'kraken',
        'treant',
        'sphinx',
    )


def test_every_line_has_four_forms_unlocking_at_the_agreed_levels():
    assert FORM_UNLOCK_LEVELS == (1, 4, 7, 10)
    assert FORM_UNLOCK_LEVELS[-1] == MAX_LEVEL

    for line in CREATURE_LINES:
        assert len(line.forms) == FORMS_PER_LINE
        assert [form.index for form in line.forms] == [1, 2, 3, 4]
        assert [form.unlock_level for form in line.forms] == list(FORM_UNLOCK_LEVELS)


def test_every_line_and_form_carries_usable_display_text():
    for line in CREATURE_LINES:
        assert line.name.strip() == line.name and line.name
        assert line.description.endswith('.')
        for form in line.forms:
            assert form.name.strip() == form.name and form.name
            # Alternative text has to describe the drawing, so a one-word
            # label or a repeat of the name would not do.
            assert len(form.alt_text) >= 30
            assert form.alt_text.endswith('.')


def test_slugs_are_url_safe_and_resolvable():
    for line in CREATURE_LINES:
        assert re.fullmatch(r'[a-z][a-z-]*[a-z]', line.slug)
        assert line_for_slug(line.slug) is line


def test_an_unknown_slug_resolves_to_none_rather_than_raising():
    assert line_for_slug('warhammer-40k-soldier') is None
    assert line_for_slug('') is None
    assert line_for_slug(None) is None


def test_asset_paths_are_derived_and_unique():
    paths = [form.asset_path for _, form in all_forms()]

    assert len(paths) == EXPECTED_LINE_COUNT * FORMS_PER_LINE
    assert len(set(paths)) == len(paths)
    for line, form in all_forms():
        assert form.asset_path == f'/creatures/{line.slug}/form-{form.index}.svg'


def test_every_referenced_drawing_is_committed_and_well_formed():
    for _, form in all_forms():
        path = asset_file(form)

        assert path.is_file(), f'missing drawing for {form.asset_path}'
        raw = path.read_bytes()
        assert 0 < len(raw) <= MAX_ASSET_BYTES, form.asset_path

        # Plain ASCII, like every other file in this repository.
        text = raw.decode('ascii')
        root = ElementTree.fromstring(text)

        assert root.tag == SVG_NAMESPACE, form.asset_path
        assert root.get('viewBox') == EXPECTED_VIEW_BOX, form.asset_path
        # A fixed width or height would stop the interface sizing a drawing
        # for the gallery and for the chooser from the same file.
        assert root.get('width') is None and root.get('height') is None


def test_no_drawing_reaches_outside_itself_or_carries_script():
    """The drawings are inert artwork, not documents that fetch or run things.

    The SVG namespace declaration is the one URL any of them may carry, so it
    is removed before the check rather than excused by it.
    """
    for _, form in all_forms():
        text = (
            asset_file(form)
            .read_text(encoding='ascii')
            .lower()
            .replace(SVG_NAMESPACE_DECLARATION, '')
        )

        for forbidden in (
            '<script',
            '<image',
            '<use',
            '<foreignobject',
            'href',
            'http',
            'url(',
        ):
            assert forbidden not in text, f'{form.asset_path} contains {forbidden}'
        assert re.search(r'\son[a-z]+\s*=', text) is None, form.asset_path


def test_the_asset_directory_holds_nothing_the_catalogue_does_not_name():
    committed = sorted(
        path.relative_to(ASSET_ROOT).as_posix()
        for path in ASSET_ROOT.rglob('*')
        if path.is_file()
    )
    expected = sorted(
        form.asset_path.removeprefix('/creatures/') for _, form in all_forms()
    )

    assert committed == expected
