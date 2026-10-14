import hashlib
import json
from pathlib import Path

import pytest

from rsc import updater

ZIP = b"PK pretend app"
SHA = hashlib.sha256(ZIP).hexdigest()


def release(tag="v0.3.0", assets=True):
    a = [{"name": updater.ASSET, "browser_download_url": "https://x/zip"},
         {"name": updater.ASSET_SHA, "browser_download_url": "https://x/sha"}] if assets else []
    return json.dumps({"tag_name": tag, "body": "Bigger buttons.", "assets": a}).encode()


def fake(rel, zip_bytes=ZIP, sha=SHA):
    files = {updater.API: rel, "https://x/zip": zip_bytes, "https://x/sha": f"{sha}  RSC-mac.zip\n".encode()}
    return lambda url: files[url]


def test_versions_compare_as_numbers_not_text():
    assert updater.parse_version("v0.10.0") > updater.parse_version("0.9.9")
    assert updater.parse_version("nightly") < updater.parse_version("0.0.1")


def test_a_newer_release_is_found_and_an_older_one_is_not():
    new = updater.check(fake(release("v0.3.0")), current="0.2.0")
    assert new["newer"] and new["latest"] == "0.3.0" and new["notes"] == "Bigger buttons."
    assert not updater.check(fake(release("v0.2.0")), current="0.2.0")["newer"]
    assert not updater.check(fake(release("v0.1.0")), current="0.2.0")["newer"]


def test_a_release_without_its_files_is_not_offered():
    r = updater.check(fake(release("v0.3.0", assets=False)), current="0.2.0")
    assert "isn't ready" in r["error"]


def test_no_internet_gives_a_plain_message():
    def offline(url):
        raise OSError("down")
    assert "Couldn't reach GitHub" in updater.check(offline)["error"]


def test_download_is_kept_only_if_it_matches_its_fingerprint(tmp_path):
    info = updater.check(fake(release()), current="0.2.0")
    path = updater.download(info, tmp_path, fake(release()))
    assert path.read_bytes() == ZIP
    with pytest.raises(RuntimeError, match="fingerprint"):
        updater.download(info, tmp_path, fake(release(), zip_bytes=b"tampered"))


def test_swap_script_waits_for_the_app_then_replaces_and_reopens(tmp_path):
    s = updater.swap_script(tmp_path / "w" / "RSC-mac.zip", Path("/Applications/RSC.app"), 4242)
    assert "kill -0 4242" in s and "ditto -x -k" in s and "xattr -dr com.apple.quarantine" in s
    assert s.index("mv /Applications/RSC.app") < s.index("/usr/bin/open /Applications/RSC.app")
    assert "rm -rf" in s


def test_install_refuses_outside_the_mac_app(tmp_path):
    with pytest.raises(RuntimeError, match="installed RSC app"):
        updater.install({"url": "u", "sha_url": "s"}, lambda: None)


def test_update_page_and_banner(cfg):
    from rsc import desktop
    from .test_web import client_and_token  # noqa: F401  (the app is built below, with the updater attached)
    cfg = desktop.first_run_setup(cfg)
    server = desktop.start_server(cfg, 0)
    server.app.testing = True
    try:
        c = server.app.test_client()
        html = c.get("/").get_data(as_text=True)
        assert "Update now" not in html                      # nothing checked yet, so no banner
        # the page itself can't reach GitHub in tests; it must still render and say so plainly
        import rsc.updater as u
        orig = u._fetch
        u._fetch = fake(release("v9.9.9"))
        try:
            page = c.get("/update").get_data(as_text=True)
            assert "Version 9.9.9 is ready" in page and "isn't the installed Mac app" in page
            assert "RSC 9.9.9 is ready" in c.get("/").get_data(as_text=True)   # banner on every page now
        finally:
            u._fetch = orig
    finally:
        server.shutdown()
