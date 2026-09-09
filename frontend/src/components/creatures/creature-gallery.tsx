/**
 * The creature gallery (issue #66).
 *
 * The form a child is on, shown large, and all four forms of their line
 * below it: the ones reached as drawings, the ones still to come as
 * silhouettes with the level that reveals them. Nothing is hidden from the
 * layout, so the shape of the whole climb is visible from the first day.
 *
 * A silhouette is a CSS filter over the same drawing, so a locked form costs
 * no second file. Its alternative text is empty and the level is written in
 * words beside it: a screen reader hears "Locked until level 7", not a
 * description of a drawing the child has not earned, and the state is never
 * carried by appearance alone.
 */

import type { Creature, CreatureForm } from '../../api/creatures'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../ui/card'

export interface CreatureGalleryProps {
  creature: Creature
}

const lockedLabel = (form: CreatureForm) => `Locked until level ${form.unlock_level}`

function FormTile({ form }: { form: CreatureForm }) {
  return (
    <li className="creature-tile">
      <img
        alt={form.unlocked ? form.alt_text : ''}
        className={
          form.unlocked
            ? 'creature-drawing creature-drawing-tile'
            : 'creature-drawing creature-drawing-tile creature-drawing-locked'
        }
        src={form.asset_path}
      />
      <span className="creature-tile-name">
        {form.unlocked ? form.name : 'Not yet'}
      </span>
      <span className="creature-tile-level">
        {form.unlocked ? `Level ${form.unlock_level}` : lockedLabel(form)}
      </span>
    </li>
  )
}

export function CreatureGallery({ creature }: CreatureGalleryProps) {
  const { current_form: currentForm, forms, level, line, max_level: maxLevel } = creature

  if (line === null) {
    return null
  }

  const nextForm = forms.find((form) => !form.unlocked)

  return (
    <div className="creature-gallery">
      <Card className="creature-card">
        <CardHeader>
          <CardTitle>
            <h2>{currentForm === null ? line.name : currentForm.name}</h2>
          </CardTitle>
          <CardDescription>
            {currentForm === null
              ? `Your ${line.name.toLowerCase()} appears at level ${forms[0].unlock_level}. You are level ${level}.`
              : `Level ${level} of ${maxLevel}. ${line.description}`}
          </CardDescription>
        </CardHeader>
        <CardContent className="creature-card-content">
          <img
            alt={currentForm === null ? '' : currentForm.alt_text}
            className={
              currentForm === null
                ? 'creature-drawing creature-drawing-current creature-drawing-locked'
                : 'creature-drawing creature-drawing-current'
            }
            src={(currentForm ?? forms[0]).asset_path}
          />
          <p className="creature-next">
            {nextForm === undefined
              ? 'This is the last form. Your creature is fully grown.'
              : `Next form at level ${nextForm.unlock_level}.`}
          </p>
        </CardContent>
      </Card>
      <h2 className="creature-forms-heading">All forms</h2>
      <ul className="creature-forms">
        {forms.map((form) => (
          <FormTile form={form} key={form.index} />
        ))}
      </ul>
    </div>
  )
}
