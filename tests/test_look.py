from rsc import prefs

from .test_web import client_and_token


def test_defaults_are_the_jobsite_look(cfg):
    c, _ = client_and_token(cfg)
    html = c.get("/").get_data(as_text=True)
    assert 'data-font="jobsite"' in html and 'data-size="normal"' in html and 'data-theme="auto"' in html


def test_a_choice_is_saved_and_shows_on_every_page(cfg, conn):
    c, token = client_and_token(cfg)
    r = c.post("/look", data={"csrf": token, "size": "xlarge", "font": "easy", "theme": "dark"})
    assert r.status_code == 204
    for path in ("/", "/jobs", "/setup"):
        html = c.get(path).get_data(as_text=True)
        assert 'data-size="xlarge"' in html and 'data-font="easy"' in html and 'data-theme="dark"' in html, path
    assert prefs.look(conn)["accent"] == "amber"   # what wasn't touched keeps its default


def test_made_up_values_are_ignored(cfg, conn):
    c, token = client_and_token(cfg)
    c.post("/look", data={"csrf": token, "size": "<script>", "font": "comic-sans"})
    assert prefs.look(conn)["size"] == "normal" and prefs.look(conn)["font"] == "jobsite"


def test_saving_the_look_needs_the_page_token(cfg):
    c, _ = client_and_token(cfg)
    assert c.post("/look", data={"size": "large"}).status_code in (400, 403)
