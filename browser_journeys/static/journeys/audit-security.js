/**
 * The current-scope security audit's live probes (T095).
 *
 * The backend suite already proves the permission matrix with Django's test
 * client. What that cannot show is what a real browser, holding a real
 * session cookie, actually gets back over the wire. These probes run inside
 * the signed-in application's own origin and check the answers a hostile
 * script in that page would receive: cross-role reads, a missing CSRF token,
 * the response headers, and whether a refusal leaks anything.
 *
 * Like the accessibility audit, this journey reports rather than asserts.
 * Findings are recorded in the write-up and fixed in their own entries.
 */
window.CHORUM_JOURNEYS['audit-security'] = async function (t) {
  var findings = []

  function note(area, rule, detail) {
    t.findings.push({ screen: area, rule: rule, detail: detail })
    findings.push(detail)
  }

  async function probe(path, options) {
    var response = await t.win().fetch(path, options || { method: 'GET' })
    var body = await response.text()
    return { status: response.status, body: body, headers: response.headers }
  }

  function expectStatus(area, path, actual, wanted, rule) {
    if (actual === wanted) {
      t.record(area + ': ' + path + ' answered ' + actual + ' as required')
      return
    }
    note(area, rule, path + ' answered ' + actual + ', expected ' + wanted)
  }

  await t.signIn(t.dataset.child, 'Chores')

  // A child's own session must not reach a parent surface, whatever the
  // interface chooses to show. These are the matrix rows a hostile script in
  // the child's page would try first.
  var parentOnly = [
    ['/api/v1/audit/', 'read audit history'],
    ['/api/v1/approvals/', 'read the approval queue'],
    ['/api/v1/household-members/', 'read the account directory'],
  ]
  for (var index = 0; index < parentOnly.length; index += 1) {
    var route = parentOnly[index]
    var denied = await probe(route[0])
    expectStatus(
      'child session',
      route[0],
      denied.status,
      403,
      'household-role isolation',
    )
    if (denied.body.indexOf(t.dataset.parent.username) !== -1) {
      note(
        'child session',
        'non-enumerating denial',
        route[0] + ' refusal echoed a username',
      )
    }
    if (denied.body.length > 200) {
      note(
        'child session',
        'compact errors',
        route[0] + ' refusal body is ' + denied.body.length + ' bytes',
      )
    }
  }

  // An unsafe request without the CSRF header must be refused even though
  // the session cookie is attached automatically.
  var forged = await probe('/api/v1/submissions/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ chore: 1, idempotency_key: 'audit-probe' }),
  })
  expectStatus(
    'csrf',
    'POST /api/v1/submissions/ with no token',
    forged.status,
    403,
    'cross-site request forgery',
  )

  // And the session cookie itself must stay out of reach of script.
  if (t.doc().cookie.indexOf('sessionid=') !== -1) {
    note('cookies', 'session confidentiality', 'the session cookie is readable by script')
  } else {
    t.record('cookies: the session cookie is not readable by script')
  }

  var session = await probe('/api/v1/auth/session/')
  var headers = {
    'x-content-type-options': 'nosniff',
    'referrer-policy': 'same-origin',
    'x-frame-options': 'DENY',
  }
  Object.keys(headers).forEach(function (name) {
    var value = session.headers.get(name)
    if (value === null) {
      note('response headers', 'browser security headers', name + ' is not sent')
    } else if (value.toLowerCase() !== headers[name].toLowerCase()) {
      t.record('response headers: ' + name + ' is "' + value + '"')
    } else {
      t.record('response headers: ' + name + ' is set')
    }
  })
  // The CSP header itself, not merely its presence (S-01): it must forbid
  // inline script and restrict default-src to self, which is what the audit
  // requires and what a browser will actually enforce.
  var csp = session.headers.get('content-security-policy')
  if (csp === null) {
    note('response headers', 'browser security headers', 'content-security-policy is not sent')
  } else if (csp.indexOf("default-src 'self'") === -1) {
    note(
      'response headers',
      'browser security headers',
      'content-security-policy does not restrict default-src to self: "' + csp + '"',
    )
  } else if (csp.indexOf('unsafe-inline') !== -1 || csp.indexOf('unsafe-eval') !== -1) {
    note(
      'response headers',
      'browser security headers',
      'content-security-policy allows inline or eval script: "' + csp + '"',
    )
  } else {
    t.record(
      'response headers: content-security-policy forbids inline script and restricts default-src to self',
    )
  }

  // Strict-Transport-Security is production-only (SECURE_HSTS_SECONDS is 0
  // outside production, exactly like the cookie Secure flags), and this
  // harness always runs in development, so it is never sent here. S-02's
  // regression test is `config/tests/test_settings.py`, which does run
  // against a production configuration; this probe only records the fact.
  if (session.headers.get('strict-transport-security') === null) {
    t.record('response headers: strict-transport-security is not sent (development only)')
  } else {
    t.record('response headers: strict-transport-security is set')
  }

  // A signed-out caller must get nothing at all from a product route.
  await t.signOut()
  var anonymous = await probe('/api/v1/chores/')
  expectStatus(
    'signed out',
    '/api/v1/chores/',
    anonymous.status,
    403,
    'default deny',
  )

  t.record('ran the live security probes; ' + t.findings.length + ' finding(s)')
}
