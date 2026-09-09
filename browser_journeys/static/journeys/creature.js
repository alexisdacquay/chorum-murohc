/**
 * A child picks a creature, and a child who has earned sees it evolve
 * (T092 and T093).
 *
 * Two children in one household, because a creature cannot be earned into a
 * new form inside one browser sitting: the first has never chosen and proves
 * onboarding, the second already holds the points for level 1 and proves
 * that the level, the celebration and the newly revealed form all agree.
 */
window.CHORUM_JOURNEYS['creature'] = async function (t) {
  await t.signIn(t.dataset.chooser, 'Chores')
  await t.goTo('Creature', 'Choose your creature')
  await t.waitForText(
    'Pick one to look after.',
    'a child who has not chosen is offered the chooser',
  )

  var options = t.doc().querySelectorAll('.creature-chooser-option')
  t.expect(options.length >= 2, 'more than one creature line is offered')
  var previews = t.doc().querySelectorAll('.creature-chooser-option img')
  t.expect(
    previews.length === options.length,
    'every offered line carries a preview drawing',
  )
  t.expect(
    Array.prototype.every.call(previews, function (image) {
      return image.getAttribute('alt') !== null && image.alt !== ''
    }),
    'every preview drawing has an accessible name',
  )

  var chosenName = options[0].querySelector('.creature-chooser-name').textContent.trim()
  options[0].click()
  var confirm = await t.dialog('Choose the ' + chosenName + '?')
  t.expect(
    confirm.innerText.indexOf('You cannot swap it for another one later.') !== -1,
    'the chooser warns that the choice is kept',
  )
  await t.click('Yes, choose this one', confirm)

  await t.waitForText('All forms', 'the chosen creature replaces the chooser')
  t.expectNoText(
    'Pick one to look after.',
    'the chooser is not offered again once a line is saved',
  )

  // A fresh load of the whole application, because a write-once choice has
  // to survive one. The route is reached by navigating rather than by a deep
  // link: a deep link into a route is rewritten to the role's start path
  // while the session is still loading, which is recorded as
  // finding A-03 in _docs/audit-accessibility.md.
  await t.load('/')
  await t.goTo('Creature')
  await t.waitForText('All forms', 'the saved choice is still there after a reload')
  t.expectNoText(
    'Pick one to look after.',
    'a reload does not offer the choice a second time',
  )

  await t.signOut()
  await t.load('/')

  await t.signIn(t.dataset.evolved, 'Chores')
  await t.goTo('Levels')
  var celebration = await t.dialog('Level up!')
  t.expect(
    celebration.innerText.indexOf('You reached level ' + t.dataset.evolvedLevel) !== -1,
    'the child who earned is told they reached level ' + t.dataset.evolvedLevel,
  )
  await t.click('Nice!', celebration)
  await t.noDialog()
  await t.waitForText(
    'Level ' + t.dataset.evolvedLevel + ' of 10',
    'the levels screen states the level reached',
  )
  await t.waitForText(
    t.dataset.evolvedLifetimePoints + ' points earned in total',
    'the levels screen states the lifetime points behind it',
  )

  await t.goTo('Creature')
  await t.waitForText('All forms', 'the earned creature is shown, not the chooser')
  await t.waitForText(
    'Level ' + t.dataset.evolvedLevel + ' of 10',
    'the creature screen agrees with the level',
  )
  await t.waitForText(
    'Next form at level 4',
    'the next form and the level that reveals it are named',
  )

  var tiles = t.doc().querySelectorAll('.creature-tile')
  t.expect(tiles.length === 4, 'all four forms of the line are laid out');
  t.expect(
    tiles[0].innerText.indexOf('Level 1') !== -1,
    'the form reached at level 1 is unlocked',
  )
  t.expect(
    tiles[1].innerText.indexOf('Locked until level 4') !== -1,
    'a form still to come says which level reveals it',
  )
  var lockedImage = tiles[1].querySelector('img')
  t.expect(
    lockedImage.getAttribute('alt') === '',
    'a locked drawing is not described to a screen reader',
  )
}
