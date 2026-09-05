from django.apps import apps
from django.test import SimpleTestCase


class ChoresAppConfigTests(SimpleTestCase):
    def test_chores_app_is_installed(self):
        config = apps.get_app_config('chores')

        self.assertEqual(config.name, 'chores')
