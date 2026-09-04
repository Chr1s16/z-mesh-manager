import importlib
from pathlib import Path

def test_health_and_ui(tmp_path, monkeypatch):
    monkeypatch.setenv("ZMM_DATA_DIR", str(tmp_path))
    import app.core, app.main
    importlib.reload(app.core)
    importlib.reload(app.main)
    from fastapi.testclient import TestClient
    with TestClient(app.main.app) as client:
        assert client.get("/api/health").json() == {"ok": True}
        page = client.get("/")
        assert page.status_code == 200
        assert "Z-Mesh Manager" in page.text
        assert 'data-view="maintenance"' in page.text
        assert 'id="job-percent"' in page.text
        assert (tmp_path / "config" / "api-token").exists()

def test_host_helper_cleans_credentials_and_tailscale_firewall():
    helper = (Path(__file__).parents[1] / "host" / "host-helper.sh").read_text()
    assert "trap 'rm -f \"$DATA/locks/request-credential\"' EXIT" in helper
    assert "/usr/bin/tailscaled --cleanup" in helper
    assert "iptables-legacy -D INPUT -j ts-input" in helper
