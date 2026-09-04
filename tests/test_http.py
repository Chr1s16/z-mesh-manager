import importlib

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
        assert (tmp_path / "config" / "api-token").exists()
