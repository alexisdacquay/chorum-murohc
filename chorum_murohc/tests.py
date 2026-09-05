from django.apps import apps
from django.test import SimpleTestCase


class ChorumMurohcAppConfigTests(SimpleTestCase):
    def test_chorum_murohc_app_is_installed(self):
        config = apps.get_app_config('chorum_murohc')

        self.assertEqual(config.name, 'chorum_murohc')
        self.assertEqual(config.verbose_name, 'chorum-murohc')
