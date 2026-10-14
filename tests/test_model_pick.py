from rsc import config, models

from .test_web import client_and_token

HAVE = {"llama3.1:8b", "llama3.2:3b", "qwen2.5vl:3b", "gemma3:12b"}


def test_automatic_unless_a_model_is_picked(cfg, conn, monkeypatch):
    cfg.model.name, cfg.model.vision = "llama3.2:3b", "qwen2.5vl:3b"
    models.apply_choice(cfg)
    assert (cfg.model.name, cfg.model.vision) == ("llama3.2:3b", "qwen2.5vl:3b")
    conn.execute("INSERT INTO settings (key, value) VALUES ('model_text', 'gemma3:12b')")
    conn.commit()
    models.apply_choice(cfg)
    assert cfg.model.name == "gemma3:12b" and cfg.model.vision == "qwen2.5vl:3b"
    conn.execute("UPDATE settings SET value = '' WHERE key = 'model_text'")   # back to automatic
    conn.commit()
    models.apply_choice(cfg)
    assert cfg.model.name == "llama3.2:3b"


def test_setup_page_lists_models_and_saves_the_pick(cfg, monkeypatch):
    cfg.model.name, cfg.model.vision = "llama3.2:3b", "qwen2.5vl:3b"
    monkeypatch.setattr(models, "ollama_installed", lambda url: set(HAVE))
    c, token = client_and_token(cfg)
    page = c.get("/setup").get_data(as_text=True)
    assert "gemma3:12b" in page and "Automatic (llama3.2:3b)" in page
    r = c.post("/setup/models", data={"csrf": token, "text_model": "gemma3:12b", "vision_model": ""}, follow_redirects=True)
    assert "Saved. Reading and writing now uses gemma3:12b." in r.get_data(as_text=True)
    assert cfg.model.name == "gemma3:12b"
    # a different process (the background mail check) loads config.toml afresh and still gets the pick
    other = config.Config(home=cfg.home)
    other.model.name = "llama3.2:3b"
    models.apply_choice(other)
    assert other.model.name == "gemma3:12b"


def test_a_model_that_is_not_on_this_mac_is_refused(cfg, monkeypatch):
    cfg.model.name = "llama3.2:3b"
    monkeypatch.setattr(models, "ollama_installed", lambda url: set(HAVE))
    c, token = client_and_token(cfg)
    r = c.post("/setup/models", data={"csrf": token, "text_model": "nope:1b", "vision_model": ""}, follow_redirects=True)
    assert "isn&#39;t one of the models on this Mac" in r.get_data(as_text=True)
    assert cfg.model.name == "llama3.2:3b"


def test_setup_says_so_when_ollama_is_off(cfg, monkeypatch):
    monkeypatch.setattr(models, "ollama_installed", lambda url: None)
    c, token = client_and_token(cfg)
    assert "open the Ollama app first" in c.get("/setup").get_data(as_text=True)
    r = c.post("/setup/models", data={"csrf": token, "text_model": "gemma3:12b"}, follow_redirects=True)
    assert "Ollama isn&#39;t running" in r.get_data(as_text=True)
