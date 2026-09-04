from app.models import ActionRequest, SettingsRequest
import pytest
import app.core as core
import os

def test_actions_are_allowlisted():
    assert ActionRequest(provider="tailscale", action="repair").action == "repair"
    with pytest.raises(Exception): ActionRequest(provider="tailscale", action="shell")

def test_settings_bounds():
    assert SettingsRequest(update_check_hours=24).update_check_hours == 24
    with pytest.raises(Exception): SettingsRequest(update_check_hours=0)

def test_staged_secret_is_root_only_and_always_removed(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "DATA", tmp_path)
    (tmp_path / "locks").mkdir()
    with pytest.raises(RuntimeError):
        with core.staged_secret("one-time-secret") as path:
            assert path.read_text() == "one-time-secret"
            if os.name == "posix":
                assert path.stat().st_mode & 0o777 == 0o600
            raise RuntimeError("simulated failure")
    assert not (tmp_path / "locks" / "request-credential").exists()
