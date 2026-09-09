"""Tests for the Content-Security-Policy middleware (S-01).

The live browser probe in `browser_journeys/static/journeys/audit-security.js`
proves this over the wire, in both environments the harness can reach. This
proves the same header at the unit level, and proves the one behaviour a
browser probe cannot: that a view which sets its own policy is respected
rather than overridden.
"""

from django.http import HttpResponse
from django.test import Client, RequestFactory

from config.middleware import CONTENT_SECURITY_POLICY, content_security_policy


def test_every_response_carries_a_policy_that_forbids_inline_script():
    response = Client().get('/api/v1/health/')

    assert response['Content-Security-Policy'] == CONTENT_SECURITY_POLICY
    assert response.status_code == 200
    # `script-src` inherits from `default-src` when it is not named on its
    # own, and neither directive appears here, so no inline or third-party
    # script is ever allowed by this policy.
    for permissive_token in ("'unsafe-inline'", "'unsafe-eval'", '*'):
        assert permissive_token not in response['Content-Security-Policy']
    assert response['Content-Security-Policy'] == "default-src 'self'"


def test_a_404_still_carries_the_policy():
    response = Client().get('/api/v1/no-such-route/')

    assert response.status_code == 404
    assert response['Content-Security-Policy'] == CONTENT_SECURITY_POLICY


def test_a_view_that_sets_its_own_policy_is_never_overridden():
    def get_response(request):
        response = HttpResponse('ok')
        response['Content-Security-Policy'] = "default-src 'none'"
        return response

    request = RequestFactory().get('/')
    response = content_security_policy(get_response)(request)

    assert response['Content-Security-Policy'] == "default-src 'none'"
