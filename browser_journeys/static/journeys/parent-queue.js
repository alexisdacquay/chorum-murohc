/**
 * A parent works the approval queue on their own device (T090).
 *
 * The two submissions are already waiting when the journey starts: they were
 * seeded directly, so this suite does not repeat the child's own path
 * through the interface. What it does prove is the parent's side - the
 * queue, the PIN asked for again on every single decision, one approval, one
 * rejection, and the empty state that follows.
 */
window.CHORUM_JOURNEYS['parent-queue'] = async function (t) {
  var approve = t.dataset.choreToApprove
  var reject = t.dataset.choreToReject

  await t.signIn(t.dataset.parent, 'Overview')
  await t.goTo('Approvals')

  await t.waitForText(approve.name, 'the queue shows the first waiting chore')
  await t.waitForText(reject.name, 'the queue shows the second waiting chore')
  await t.waitForText(
    t.dataset.child.username,
    'each queued item names the child who submitted it',
  )

  await t.click('Approve ' + approve.name + ' for ' + t.dataset.child.username)
  var approval = await t.dialog('Approve "' + approve.name + '"')
  await t.fill('Your PIN', '999999', approval)
  await t.click('Approve', approval)
  await t.waitForText(
    'That PIN was not accepted.',
    'a wrong PIN is refused on the parent device too',
  )

  await t.fill('Your PIN', t.dataset.parent.pin, approval)
  await t.click('Approve', approval)
  await t.waitForText(
    'Approved "' + approve.name + '".',
    'the parent approves with their own PIN',
  )
  await t.noDialog()

  await t.click('Reject ' + reject.name + ' for ' + t.dataset.child.username)
  var rejection = await t.dialog('Reject "' + reject.name + '"')
  t.expect(
    rejection.innerText.indexOf('Enter your approval PIN to confirm.') !== -1,
    'the PIN is asked for again for the second decision, never remembered',
  )
  await t.fill('Your PIN', t.dataset.parent.pin, rejection)
  await t.fill('Reason (optional)', 'Half the garden is still covered.', rejection)
  await t.click('Reject', rejection)
  await t.waitForText(
    'Rejected "' + reject.name + '".',
    'the parent rejects the second chore',
  )
  await t.noDialog()

  await t.waitForText(
    'Nothing is waiting for a decision.',
    'the queue is empty once both decisions are made',
  )
  t.expect(
    t.doc().querySelectorAll('.approval-queue-card').length === 0,
    'neither decided chore is left in the queue',
  )
}
