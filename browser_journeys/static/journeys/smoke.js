/**
 * The non-product smoke journey (T088).
 *
 * It proves the harness itself, not a household rule: the built frontend is
 * served, the API answers on the same origin, the session cookie and the
 * CSRF token survive a real sign-in, the data this run created is its own,
 * and the run can end cleanly. No chore, point, reward or creature is
 * touched.
 */
window.CHORUM_JOURNEYS['smoke'] = async function (t) {
  await t.waitForText('Sign in', 'the signed-out application is served')

  t.expect(
    t.dataset.household.indexOf(t.all.token) !== -1,
    'this run owns a household named after its own run token',
  )

  await t.signIn(t.dataset.parent, 'Overview')
  t.expect(
    t.doc().cookie.indexOf('csrftoken=') !== -1,
    'the CSRF cookie is readable on the same origin',
  )
  t.expect(
    t.doc().cookie.indexOf('sessionid=') === -1,
    'the session cookie stays out of reach of script',
  )

  await t.signOut()
}
