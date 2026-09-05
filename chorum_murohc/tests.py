import ast
from importlib.util import resolve_name
from pathlib import Path
from unittest.mock import patch

from django.apps import apps
from django.conf import settings
from django.test import SimpleTestCase


PRODUCT_PACKAGE = Path(__file__).resolve().parent
ROOT_PACKAGE = 'chorum_murohc'
ROOT_PACKAGE_MODULES = frozenset(
    {'__init__', 'admin', 'apps', 'migrations', 'models', 'views'}
)

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


def _boundary_from_module(module):
    parts = module.split('.')
    if not parts or parts[0] != ROOT_PACKAGE:
        return None
    if len(parts) == 1:
        return ROOT_PACKAGE
    if parts[1] in ALLOWED_DOMAIN_IMPORTS:
        return parts[1]
    if parts[1] in ROOT_PACKAGE_MODULES:
        return ROOT_PACKAGE
    return f'{ROOT_PACKAGE}.{parts[1]}'


def _imported_boundaries(path):
    tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    source_package = _source_package(path)
    imported_boundaries = set()

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
            if module == ROOT_PACKAGE:
                modules.extend(
                    module
                    if alias.name == '*'
                    else f'{module}.{alias.name}'
                    for alias in node.names
                )
            else:
                modules.append(module)

        for module in modules:
            boundary = _boundary_from_module(module)
            if boundary is not None:
                imported_boundaries.add(boundary)

    return imported_boundaries


def _disallowed_imports(source_boundary, imported_boundaries):
    allowed_imports = ALLOWED_DOMAIN_IMPORTS.get(
        source_boundary,
        frozenset(),
    )
    return {
        imported_boundary
        for imported_boundary in imported_boundaries
        if imported_boundary != source_boundary
        and imported_boundary not in allowed_imports
    }


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
    def _scan_source(self, source_domain, source):
        path = PRODUCT_PACKAGE / source_domain / 'boundary_probe.py'
        with patch.object(Path, 'read_text', return_value=source):
            return _imported_boundaries(path)

    def test_scanner_reports_undeclared_product_package(self):
        imported_packages = self._scan_source(
            'identity',
            'import chorum_murohc.unapproved',
        )

        self.assertEqual(
            imported_packages,
            {'chorum_murohc.unapproved'},
        )
        self.assertEqual(
            _disallowed_imports('identity', imported_packages),
            {'chorum_murohc.unapproved'},
        )

    def test_scanner_reports_domain_to_root_import(self):
        imported_packages = self._scan_source(
            'audit',
            'import chorum_murohc',
        )

        self.assertEqual(imported_packages, {'chorum_murohc'})
        self.assertEqual(
            _disallowed_imports('audit', imported_packages),
            {'chorum_murohc'},
        )

    def test_scanner_keeps_every_approved_import_allowed(self):
        for source_domain, allowed_imports in ALLOWED_DOMAIN_IMPORTS.items():
            source_lines = [f'import chorum_murohc.{source_domain}']
            source_lines.extend(
                f'from chorum_murohc import {target}'
                for target in sorted(allowed_imports)
            )
            source = '\n'.join(source_lines)

            with self.subTest(source_domain=source_domain):
                imported_packages = self._scan_source(source_domain, source)
                self.assertEqual(
                    imported_packages,
                    {source_domain, *allowed_imports},
                )
                self.assertEqual(
                    _disallowed_imports(source_domain, imported_packages),
                    set(),
                )

    def test_product_imports_follow_approved_directions(self):
        violations = []

        for path in sorted(PRODUCT_PACKAGE.rglob('*.py')):
            if _is_test_source(path):
                continue

            relative_path = path.relative_to(PRODUCT_PACKAGE)
            source_boundary = (
                relative_path.parts[0]
                if relative_path.parts[0] in ALLOWED_DOMAIN_IMPORTS
                else ROOT_PACKAGE
            )

            imported_boundaries = _imported_boundaries(path)
            for imported_boundary in sorted(
                _disallowed_imports(source_boundary, imported_boundaries)
            ):
                violations.append(
                    f'{relative_path}: {source_boundary} -> {imported_boundary}'
                )

        self.assertEqual(violations, [])
