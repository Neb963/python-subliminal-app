from pathlib import Path

import pytest

from subliminal.autostart import _quote_desktop_arg, autostart_path, set_autostart


def test_quote_desktop_arg_handles_spaces_and_percent() -> None:
    assert _quote_desktop_arg("/usr/bin/subliminal") == "/usr/bin/subliminal"
    assert (
        _quote_desktop_arg("/home/my user/bin/subliminal")
        == '"/home/my user/bin/subliminal"'
    )
    assert (
        _quote_desktop_arg("/tmp/100% done/app")
        == '"/tmp/100%% done/app"'
    )


def test_set_autostart_writes_quoted_exec(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    exe = tmp_path / "my dir" / "subliminal"
    monkeypatch.setenv("SUBLIMINAL_EXECUTABLE", str(exe))

    set_autostart(True)
    desktop = autostart_path()
    assert desktop.exists()
    content = desktop.read_text(encoding="utf-8")
    assert f'Exec="{exe.resolve()}" --background' in content

    set_autostart(False)
    assert not desktop.exists()
