"""Proofs for the harness server's own routing and path handling."""

from pathlib import Path

from browser_journeys.serve_app import _query, _safe_child


def test_a_query_value_is_read_by_name():
    environ = {'QUERY_STRING': 'journey=reward&other=1'}

    assert _query(environ, 'journey') == 'reward'
    assert _query(environ, 'missing') == ''


def test_a_path_inside_the_root_resolves(tmp_path):
    (tmp_path / 'assets').mkdir()
    (tmp_path / 'assets' / 'app.js').write_text('x')

    assert _safe_child(tmp_path, '/assets/app.js') == tmp_path / 'assets' / 'app.js'


def test_the_root_itself_resolves(tmp_path):
    assert _safe_child(tmp_path, '/') == tmp_path


def test_a_path_climbing_out_of_the_root_is_refused(tmp_path):
    root = tmp_path / 'dist'
    root.mkdir()
    (tmp_path / 'secret.txt').write_text('x')

    assert _safe_child(root, '/../secret.txt') is None
    assert _safe_child(root, '/assets/../../secret.txt') is None


def test_an_absolute_looking_path_stays_inside_the_root(tmp_path):
    resolved = _safe_child(tmp_path, '/etc/passwd')

    assert resolved is not None
    assert Path(tmp_path) in resolved.parents
