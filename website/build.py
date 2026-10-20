"""Build the website: posts and pages -> dist/ -> public/ (what rscrafters.com serves).

    python3 build.py

Runs build_blog.py (posts, blog index, sitemap), check_blog.py (broken links, banned claims) and make_deploy.py
(strips draft notes, leaves out pages on hold). Stops at the first step that fails. Cloudflare runs this same command
on every push, so if it passes here it will publish.
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
for step in ("build_blog.py", "check_blog.py", "make_deploy.py"):
    print(f"== {step}", flush=True)
    if subprocess.run([sys.executable, str(HERE / step)], cwd=HERE).returncode:
        sys.exit(f"{step} failed; nothing to publish until it passes.")
