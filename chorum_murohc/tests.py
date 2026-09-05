import ast
from importlib.util import resolve_name
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.test import SimpleTestCase


PRODUCT_PACKAGE = Path(__file__).resolve().parent

APP_CONFIGS = {
    'chorum_murohc': (
        'chorum_murohc.apps.ChorumMurohcConfig',
        'chorum_murohc',
    ),
    'chorum_murohc.identity': (
        'chorum_murohc.identity.apps.IdentityConfig',
        'identity',
    ),
    'chorum_murohc.audit': (
        'chorum_murohc.audit.apps.AuditConfig',
        'audit',
    ),
    'chorum_murohc.chores': (
        'chorum_murohc.chores.apps.ChoresConfig',
        'chores',
    ),
    'chorum_murohc.submissions': (
        'chorum_murohc.submissions.apps.SubmissionsConfig',
        'submissions',
    ),
    'chorum_murohc.ledger': (
        'chorum_murohc.ledger.apps.LedgerConfig',
        'ledger',
    ),
    'chorum_murohc.rewards': (
        'chorum_murohc.rewards.apps.RewardsConfig',
        'rewards',
    ),
    'chorum_murohc.progression': (
        'chorum_murohc.progression.apps.ProgressionConfig',
        'progression',
    ),
    'chorum_murohc.creatures': (
        'chorum_murohc.creatures.apps.CreaturesConfig',
        'creatures',
    ),
}

ALLOWED_DOMAIN_IMPORTS = {
    'audit': frozenset(),
    'identity': frozenset({'audit'}),
    'chores': frozenset({'audit'}),
    'ledger': frozenset({'audit'}),
    'submissions': frozenset({'identity', 'chores', 'ledger', 'audit'}),
    'rewards': frozenset({'identity', 'ledger', 'audit'}),
    'progression': frozenset({'identity', 'ledger', 'audit'}),
    'creatures': frozenset({'identity', 'progression', 'audit'}),
}


def _source_package(path):
    relative_parts = path.relative_to(PRODUCT_PACKAGE).with_suffix('').parts
    return '.'.join(('chorum_murohc', *relative_parts[:-1]))


def _domain_from_module(module):
    parts = module.split('.')
    if (
        len(parts) >= 2
        and parts[0] == 'chorum_murohc'
        and parts[1] in ALLOWED_DOMAIN_IMPORTS
    ):
        return parts[1]
    return None


def _imported_domains(path):
    tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    source_package = _source_package(path)
    imported_domains = set()

    for node in ast.walk(tree):
        modules = []
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                relative_name = f"{'.' * node.level}{node.module or ''}"
                module = resolve_name(relative_name, source_package)
            else:
                module = node.module or ''
            modules.append(module)
            modules.extend(f'{module}.{alias.name}' for alias in node.names)

        for module in modules:
            domain = _domain_from_module(module)
            if domain is not None:
                imported_domains.add(domain)

    return imported_domains


def _is_test_source(path):
    relative_path = path.relative_to(PRODUCT_PACKAGE)
    return (
        'tests' in relative_path.parts
        or path.name == 'tests.py'
        or path.name.startswith('test_')
        or path.name.endswith('_tests.py')
    )


class ChorumMurohcAppConfigTests(SimpleTestCase):
    def test_chorum_murohc_app_is_installed(self):
        config = apps.get_app_config('chorum_murohc')

        self.assertEqual(config.name, 'chorum_murohc')
        self.assertEqual(config.verbose_name, 'chorum-murohc')

    def test_approved_app_configs_are_registered(self):
        expected_config_paths = tuple(
            config_path for config_path, _ in APP_CONFIGS.values()
        )
        configured_product_apps = tuple(
            entry
            for entry in settings.INSTALLED_APPS
            if entry.startswith('chorum_murohc')
        )

        self.assertEqual(configured_product_apps, expected_config_paths)

        loaded_labels = []
        for name, (config_path, label) in APP_CONFIGS.items():
            with self.subTest(name=name):
                config = apps.get_app_config(label)
                loaded_config_path = (
                    f'{config.__class__.__module__}.{config.__class__.__name__}'
                )

                self.assertEqual(loaded_config_path, config_path)
                self.assertEqual(config.name, name)
                self.assertEqual(config.label, label)
                loaded_labels.append(config.label)

        self.assertEqual(len(loaded_labels), len(set(loaded_labels)))


class ProductImportBoundaryTests(SimpleTestCase):
    def test_product_imports_follow_approved_directions(self):
        violations = []

        for path in sorted(PRODUCT_PACKAGE.rglob('*.py')):
            if _is_test_source(path):
                continue

            relative_path = path.relative_to(PRODUCT_PACKAGE)
            source_domain = (
                relative_path.parts[0]
                if relative_path.parts[0] in ALLOWED_DOMAIN_IMPORTS
                else None
            )
            allowed_imports = ALLOWED_DOMAIN_IMPORTS.get(
                source_domain,
                frozenset(),
            )

            for imported_domain in sorted(_imported_domains(path)):
                if (
                    imported_domain != source_domain
                    and imported_domain not in allowed_imports
                ):
                    source_name = source_domain or 'chorum_murohc root'
                    violations.append(
                        f'{relative_path}: {source_name} -> {imported_domain}'
                    )

        self.assertEqual(violations, [])
