# Creature Catalogue Policy

Status: settled, 2026-09-08, by the product owner on
[issue 66](https://github.com/alexisdacquay/chorum-murohc/issues/66).

## The decision

This project uses no third-party intellectual property, in code, copy, names
or artwork.

The lines the original `_docs/plan.md` named - Warhammer 40k Soldier,
Warhammer Tyranid, Pikachu, Lego Star Wars Stormtrooper, Playmobil Pirate -
are dropped. Five of them were somebody else's characters, and renaming a
drawing that still reads as the original would not have changed that. The
question of licensing them was not asked and is not open: nothing here needs a
licence, so nothing here waits on one.

## The seven lines

All seven are public-domain mythological archetypes, drawn from scratch for
this repository:

| Slug | Name | Source |
| --- | --- | --- |
| `dragon` | Dragon | Mythology, no owner |
| `golem` | Golem | Folklore, no owner |
| `griffin` | Griffin | Mythology, no owner |
| `phoenix` | Phoenix | Mythology, no owner |
| `kraken` | Kraken | Folklore, no owner |
| `treant` | Treant | Folklore, no owner |
| `sphinx` | Sphinx | Mythology, no owner |

An archetype being free is not a licence to copy one particular rendering of
it. Every drawing here is an original composition of plain shapes, and none is
traced from, or drawn to resemble, any film, game or toy version of its
archetype.

## The artwork

- Four forms per line, twenty-eight files, committed to this repository at
  `frontend/public/creatures/<slug>/form-<index>.svg`.
- Flat SVG, one 96 by 96 view box, one colour family per line, a few dozen
  shapes at most, readable at 96 pixels.
- Nothing is downloaded, generated through an external service, uploaded, or
  loaded from an external image host at build time or at run time. The
  drawings are inert: no script, no external reference, no embedded raster.
- `chorum_murohc/creatures/test_catalogue.py` enforces the parts of that a
  test can enforce - every catalogue path resolves to a committed file, the
  view box is the same on all twenty-eight, no file carries a script or an
  external reference, and the directory holds nothing the catalogue does not
  name.

## What this constrains from here

- A new line or a replacement drawing is a commit to this repository, made by
  the person adding it, under the same rules. No exception for "just a
  placeholder".
- No creature asset may be produced through an external image-generation
  service, and no prompt or reference naming a protected character, franchise
  or brand may be used, whatever the intended output.
- The catalogue is code (`chorum_murohc/creatures/catalogue.py`), not
  household data. Adding or retiring a line needs a migration, because the
  database refuses a slug the catalogue does not define.
