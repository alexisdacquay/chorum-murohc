from pathlib import Path

from browser_journeys import run_journeys


def test_browser_discovery_prefers_an_executable_on_path(tmp_path, monkeypatch):
    browser = tmp_path / 'chromium'
    browser.write_text('browser')

    monkeypatch.setattr(
        run_journeys.shutil,
        'which',
        lambda command: str(browser) if command == 'chromium' else None,
    )

    assert run_journeys.discover_chrome(file_candidates=()) == str(browser)


def test_browser_discovery_falls_back_to_a_known_file(tmp_path, monkeypatch):
    browser = tmp_path / 'chrome'
    browser.write_text('browser')
    monkeypatch.setattr(run_journeys.shutil, 'which', lambda _command: None)

    assert run_journeys.discover_chrome(file_candidates=(browser,)) == str(browser)


def test_browser_discovery_reports_no_match(monkeypatch):
    monkeypatch.setattr(run_journeys.shutil, 'which', lambda _command: None)

    assert run_journeys.discover_chrome(file_candidates=()) is None


def test_default_cache_uses_the_host_temporary_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(run_journeys.tempfile, 'gettempdir', lambda: str(tmp_path))

    assert run_journeys.default_uv_cache() == tmp_path / 'chorum-murohc-uv-cache'


def test_main_explains_how_to_supply_an_undiscovered_browser(
    tmp_path, monkeypatch, capsys
):
    build = tmp_path / 'frontend' / 'dist'
    build.mkdir(parents=True)
    (build / 'index.html').write_text('built')
    monkeypatch.setattr(run_journeys, 'discover_chrome', lambda: None)

    assert run_journeys.main([str(tmp_path)]) == 2
    assert capsys.readouterr().err == 'no browser found; pass --chrome PATH\n'


def test_main_reports_an_invalid_explicit_browser(tmp_path, capsys):
    build = tmp_path / 'frontend' / 'dist'
    build.mkdir(parents=True)
    (build / 'index.html').write_text('built')
    missing = Path(tmp_path / 'missing-browser')

    assert run_journeys.main([str(tmp_path), '--chrome', str(missing)]) == 2
    assert capsys.readouterr().err == f'no browser at {missing}\n'
