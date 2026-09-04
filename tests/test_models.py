from app.models import ActionRequest, SettingsRequest
import pytest

def test_actions_are_allowlisted():
    assert ActionRequest(provider="tailscale", action="repair").action == "repair"
    with pytest.raises(Exception): ActionRequest(provider="tailscale", action="shell")

def test_settings_bounds():
    assert SettingsRequest(update_check_hours=24).update_check_hours == 24
    with pytest.raises(Exception): SettingsRequest(update_check_hours=0)
