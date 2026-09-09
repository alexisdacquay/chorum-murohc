/**
 * A child spends points on a reward (T091).
 *
 * Balance shown, an unaffordable reward refused before any request is made,
 * an affordable one redeemed, and the ledger telling the same story
 * afterwards: the exact debit, and the exact remaining balance.
 */
window.CHORUM_JOURNEYS['reward'] = async function (t) {
  var affordable = t.dataset.affordableReward
  var unaffordable = t.dataset.unaffordableReward
  var starting = t.dataset.startingBalance
  var remaining = starting - affordable.points

  await t.signIn(t.dataset.child, 'Chores')
  await t.goTo('Rewards')

  var shownBalance = await t.readTestId('rewards-balance')
  t.expect(
    shownBalance === starting + ' points available',
    'the reward screen shows the balance the ledger holds',
  )
  await t.waitForText(affordable.name, 'the affordable reward is listed')
  await t.waitForText(unaffordable.name, 'the unaffordable reward is listed too')

  await t.click('Redeem ' + unaffordable.name)
  var refused = await t.dialog('Redeem "' + unaffordable.name + '"?')
  t.expect(
    refused.innerText.indexOf('which is not enough yet') !== -1,
    'a reward beyond the balance says so',
  )
  var confirmButton = t.controls(refused).filter(function (control) {
    return control.textContent.trim() === 'Redeem'
  })[0]
  t.expect(
    confirmButton !== undefined && confirmButton.disabled,
    'the confirm button is unavailable while the points are short',
  )
  await t.click('Cancel', refused)
  await t.noDialog()

  await t.click('Redeem ' + affordable.name)
  var accepted = await t.dialog('Redeem "' + affordable.name + '"?')
  t.expect(
    accepted.innerText.indexOf(remaining + ' left after') !== -1,
    'the confirmation states what is left after the spend',
  )
  await t.click('Redeem', accepted)
  await t.waitForText(
    'Requested "' + affordable.name + '"',
    'the redemption is confirmed and waits for a parent',
  )
  await t.noDialog()

  await t.wait(
    function () {
      var element = t.doc().querySelector('[data-testid="rewards-balance"]')
      return (
        element !== null &&
        element.textContent.trim() === remaining + ' points available'
      )
    },
    'the balance to fall to ' + remaining,
  )
  t.record('the balance fell by exactly the reward cost')

  await t.goTo('Points', 'Your balance')
  var ledgerBalance = await t.readTestId('points-balance-figure')
  t.expect(
    ledgerBalance === remaining + ' points',
    'the points dashboard agrees with the reward screen',
  )
  await t.waitForText('Reward debit', 'the ledger history records the spend')
  await t.waitForText(
    '-' + affordable.points,
    'the ledger shows the exact debit of ' + affordable.points,
  )
}
