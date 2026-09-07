from django.test import SimpleTestCase
from django.urls import resolve, reverse


class HealthUrlTests(SimpleTestCase):
    def test_health_url_is_namespaced_and_resolves_to_health_view(self):
        from chorum_murohc.api.views import health

        health_path = reverse('api_v1:health')

        self.assertEqual(health_path, '/api/v1/health/')
        self.assertIs(resolve(health_path).func, health)

    def test_existing_admin_route_is_unchanged(self):
        self.assertEqual(reverse('admin:index'), '/admin/')
        self.assertEqual(resolve('/admin/').view_name, 'admin:index')

    def test_non_health_api_paths_return_not_found(self):
        for path in (
            '/api/',
            '/api/v1/',
            '/api/v2/health/',
            '/api/v1/unknown/',
        ):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 404)

    def test_missing_trailing_slash_redirects_to_canonical_url(self):
        response = self.client.get('/api/v1/health')

        self.assertEqual(response.status_code, 301)
        self.assertEqual(response.headers['Location'], '/api/v1/health/')


class HealthResponseTests(SimpleTestCase):
    health_path = '/api/v1/health/'
    allowed_methods = frozenset({'GET', 'HEAD', 'OPTIONS'})

    def assert_success_response(self, response):
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['Content-Type'], 'application/json')
        self.assertEqual(response.json(), {'status': 'ok'})

    def assert_allowed_methods(self, response):
        self.assertEqual(
            {method.strip() for method in response.headers['Allow'].split(',')},
            self.allowed_methods,
        )

    def test_unauthenticated_get_is_exact_json_and_uses_no_database(self):
        response = self.client.get(self.health_path)

        self.assert_success_response(response)
        self.assertFalse(response.cookies)
        self.assertFalse(response.wsgi_request.session.accessed)

    def test_cookie_and_malformed_authorization_do_not_change_response(self):
        self.client.cookies['unused'] = 'synthetic-cookie'

        response = self.client.get(
            self.health_path,
            headers={'authorization': 'Bearer malformed-test-value'},
        )

        self.assert_success_response(response)
        self.assertNotIn(b'synthetic-cookie', response.content)
        self.assertNotIn(b'malformed-test-value', response.content)
        self.assertFalse(response.cookies)
        self.assertFalse(response.wsgi_request.session.accessed)

    def test_json_and_wildcard_accept_headers_receive_exact_success(self):
        for accept in ('application/json', '*/*'):
            with self.subTest(accept=accept):
                response = self.client.get(
                    self.health_path,
                    headers={'accept': accept},
                )

                self.assert_success_response(response)

    def test_head_returns_success_with_empty_body(self):
        response = self.client.head(self.health_path)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['Content-Type'], 'application/json')
        self.assertEqual(response.content, b'')
        self.assert_allowed_methods(response)

    def test_options_returns_native_drf_metadata(self):
        response = self.client.options(self.health_path)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['Content-Type'], 'application/json')
        self.assert_allowed_methods(response)
        self.assertEqual(
            response.json(),
            {
                'name': 'Health',
                'description': '',
                'renders': ['application/json'],
                'parses': [
                    'application/json',
                    'application/x-www-form-urlencoded',
                    'multipart/form-data',
                ],
            },
        )

    def test_mutating_methods_return_native_method_not_allowed(self):
        for method in ('POST', 'PUT', 'PATCH', 'DELETE'):
            with self.subTest(method=method):
                response = self.client.generic(
                    method,
                    self.health_path,
                    data=b'{}',
                    content_type='application/json',
                )

                self.assertEqual(response.status_code, 405)
                self.assertEqual(
                    response.headers['Content-Type'],
                    'application/json',
                )
                self.assertEqual(
                    response.json(),
                    {'detail': f'Method "{method}" not allowed.'},
                )
                self.assert_allowed_methods(response)

    def test_html_only_accept_returns_native_not_acceptable(self):
        response = self.client.get(
            self.health_path,
            headers={'accept': 'text/html'},
        )

        self.assertEqual(response.status_code, 406)
        self.assertEqual(response.headers['Content-Type'], 'application/json')
        self.assertEqual(
            response.json(),
            {'detail': 'Could not satisfy the request Accept header.'},
        )
        self.assert_allowed_methods(response)
