/**
 * A child marks a chore done and a parent decides it on the child's device
 * (T089).
 *
 * The whole path in one sitting: sign in, attest, wait as pending, hand the
 * device over, name the approving parent, fail a PIN, pass one, see the
 * points arrive - and then the same path to a rejection that credits
 * nothing.
 */
window.CHORUM_JOURNEYS['child-submission'] = async function (t) {
  var approve = t.dataset.choreToApprove
  var reject = t.dataset.choreToReject

  await t.signIn(t.dataset.child, 'Chores')
  await t.waitForText(approve.name, 'the chore pool is visible to the child')

  await t.click('Mark ' + approve.name + ' as done')
  var confirm = await t.dialog('Mark "' + approve.name + '" as done?')
  await t.fill('Add a note (optional)', 'All tidy.', confirm)
  await t.click('Mark as done', confirm)

  await t.waitForText(
    '"' + approve.name + '" marked as done. A parent will review it.',
    'the child is told a parent will review it',
  )
  await t.waitForText('Pending review', 'the chore now shows as pending review')

  await t.click('Get ' + approve.name + ' approved now')
  var decision = await t.dialog('Get "' + approve.name + '" approved')
  await t.waitForText(
    t.dataset.parentOne.username,
    'the child device names the household parents before anyone signs in',
  )

  // The other parent's PIN must not approve for the parent who was named.
  await t.choose(t.dataset.parentOne.username)
  await t.fill('Parent PIN', t.dataset.parentTwo.pin, decision)
  await t.click('Approve', decision)
  await t.waitForText(
    'That PIN was not accepted.',
    'a PIN belonging to the other parent is refused',
  )

  await t.fill('Parent PIN', t.dataset.parentOne.pin, decision)
  await t.click('Approve', decision)
  await t.waitForText(
    '"' + approve.name + '" was approved.',
    'the named parent approves with their own PIN',
  )
  await t.noDialog()

  await t.goTo('Points', 'Your balance')
  var credited = await t.readTestId('points-balance-figure')
  t.expect(
    credited === approve.points + ' points',
    'the approved chore credited exactly ' + approve.points + ' points',
  )

  await t.goTo('Chores')
  await t.click('Mark ' + reject.name + ' as done')
  var secondConfirm = await t.dialog('Mark "' + reject.name + '" as done?')
  await t.click('Mark as done', secondConfirm)
  await t.waitForText('Pending review', 'the second chore is pending too')

  await t.click('Get ' + reject.name + ' approved now')
  var rejection = await t.dialog('Get "' + reject.name + '" approved')
  await t.choose(t.dataset.parentOne.username)
  await t.fill('Parent PIN', t.dataset.parentOne.pin, rejection)
  await t.fill('Reason if rejecting (optional)', 'Try the bottom rack too.', rejection)
  await t.click('Reject', rejection)
  await t.waitForText(
    '"' + reject.name + '" was rejected.',
    'the parent rejects the second chore',
  )

  await t.goTo('Points', 'Your balance')
  var afterRejection = await t.readTestId('points-balance-figure')
  t.expect(
    afterRejection === approve.points + ' points',
    'a rejection credited nothing',
  )
}
