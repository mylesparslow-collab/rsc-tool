from rsc import doctor, models

from .test_web import client_and_token

ONLY_OTHER = {"gemma3:12b"}   # a model the app never heard of; the defaults are not on this Mac


def _installed(monkeypatch, names):
    monkeypatch.setattr(models, "ollama_installed", lambda url: None if names is None else set(names))
    monkeypatch.setattr(models, "_sizes", lambda url: {})
    models._PILL.clear()


def test_automatic_uses_what_is_installed_not_the_default(cfg, monkeypatch):
    cfg.model.name, cfg.model.vision = "llama3.1:8b", "qwen2.5vl:3b"
    _installed(monkeypatch, ONLY_OTHER)
    models.apply_choice(cfg)
    assert cfg.model.name == "gemma3:12b" and cfg.model.vision == "gemma3:12b"
    assert all(r["ready"] for r in models.status(cfg, ONLY_OTHER) if r["role"] != "speech")


def test_the_default_wins_when_it_is_installed(cfg, monkeypatch):
    cfg.model.name = "llama3.2:3b"
    _installed(monkeypatch, {"llama3.2:3b", "gemma3:12b"})
    models.apply_choice(cfg)
    assert cfg.model.name == "llama3.2:3b"


def test_no_warning_about_a_missing_default_when_a_model_works(cfg, monkeypatch):
    cfg.model.name, cfg.model.vision = "llama3.1:8b", "qwen2.5vl:3b"
    _installed(monkeypatch, ONLY_OTHER)
    models.apply_choice(cfg)
    rows = doctor.run(cfg, include_app=False)
    text = " ".join(f"{r['name']} {r['detail']} {r.get('fix', '')}" for r in rows)
    assert "isn't downloaded" not in text
    h = models.health(cfg)
    assert h["state"] == "up" and h["suggest"] == {} and "gemma3:12b" in h["detail"]
    c, _ = client_and_token(cfg)
    for path in ("/setup", "/"):
        page = c.get(path).get_data(as_text=True)
        assert "not downloaded" not in page and "isn&#39;t downloaded" not in page
    assert "AI ready" in c.get("/").get_data(as_text=True)


def test_health_says_what_is_wrong_in_plain_words(cfg, monkeypatch):
    _installed(monkeypatch, None)
    assert models.health(cfg)["state"] == "off"
    _installed(monkeypatch, [])
    h = models.health(cfg)
    assert h["state"] == "none" and h["suggest"]["text"] == models.suggested(cfg)["text"]


def test_download_button_only_fetches_suggested_models(cfg, monkeypatch):
    started = []
    _installed(monkeypatch, [])
    monkeypatch.setattr(models, "start_download", lambda url, name: started.append(name) or True)
    monkeypatch.setattr(models, "_DOWNLOADS", {})
    c, tok = client_and_token(cfg)
    started.clear()   # opening Home with no model at all starts the automatic download; that is tested below
    c.post("/setup/models/download", data={"csrf": tok, "model": "evil/model:latest"})
    assert started == []
    c.post("/setup/models/download", data={"csrf": tok, "model": models.TEXT_SMALL})
    assert started == [models.TEXT_SMALL]


def test_progress_and_test_buttons(cfg, monkeypatch):
    _installed(monkeypatch, {"llama3.2:3b"})
    monkeypatch.setattr(models, "test_text", lambda cfg: {"ok": True, "model": "llama3.2:3b", "seconds": 1.2, "error": ""})
    c, tok = client_and_token(cfg)
    assert c.get("/setup/models/progress").get_json()["running"] is None
    assert c.post("/setup/models/test", data={"csrf": tok}).get_json()["ok"] is True
    assert "Test it" in c.get("/setup").get_data(as_text=True)


def test_auto_download_only_when_nothing_usable(cfg, monkeypatch):
    started = []
    monkeypatch.setattr(models, "start_download", lambda url, name: started.append(name) or True)
    monkeypatch.setattr(models, "_DOWNLOADS", {})
    _installed(monkeypatch, ONLY_OTHER)
    assert models.auto_download(cfg) is None                 # a working model exists
    _installed(monkeypatch, None)
    assert models.auto_download(cfg) is None                 # Ollama is off
    _installed(monkeypatch, [])
    assert models.auto_download(cfg, enabled=False) is None  # switched off on Setup
    assert models.auto_download(cfg) == models.suggested(cfg)["text"] and started == [models.suggested(cfg)["text"]]
