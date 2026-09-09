"""Response headers Django's own middleware does not add (S-01).

`django.middleware.security.SecurityMiddleware` and
`django.middleware.clickjacking.XFrameOptionsMiddleware` already cover
`X-Content-Type-Options`, `Referrer-Policy` and `X-Frame-Options`; the
security audit's "What holds" section proves all three are sent. Django 5.2
has no built-in Content-Security-Policy support, so this is the one header
this project has to add itself, without reaching for a third-party package
for a single header.

The policy is deliberately the minimum the audit asked for: `default-src
'self'`. There is no separate `script-src`, so it inherits from `default-src`
and forbids inline script and any third-party script host; there is no
`'unsafe-inline'` or `'unsafe-eval'` anywhere in the value. The frontend
serves no inline `<script>` and no remote script host, so this is not a
narrowing of anything the product already does.
"""

CONTENT_SECURITY_POLICY = "default-src 'self'"


def content_security_policy(get_response):
    """Send `CONTENT_SECURITY_POLICY` on every response that lacks one.

    `setdefault` rather than a plain assignment, so a view that ever needs a
    different policy of its own is never overridden by this default.
    """

    def middleware(request):
        response = get_response(request)
        response.setdefault('Content-Security-Policy', CONTENT_SECURITY_POLICY)
        return response

    return middleware
