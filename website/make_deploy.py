"""Make the launch copy of the website: dist/ (from build_blog.py) -> public/, which Cloudflare serves.

Usage: python3 make_deploy.py [--formspree https://formspree.io/f/XXXX] [--allow-placeholders]
Usually run through build.py.

What it does to the copy (dist/ itself is untouched):
- removes the yellow draft-notes bar and hides draft-only notes (html gets class notes-off)
- sets every form (quote, Safe at Home list) to post to Formspree when --formspree is given
- leaves out the hiring page and every link to it, and the FAQ insurance answer (Myles, 2026-10-18:
  on ice until Nick's crew and insurance setup is known)
- refuses to finish while blank placeholders ([Nick to confirm...], $__) are still in the pages
"""
import argparse, os, re, shutil, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "dist"
OUT = HERE / "public"
BLANKS = re.compile(r"\[Nick to confirm[^\]]*\]|\$_{2,}")

ap = argparse.ArgumentParser()
# the live Formspree form (Myles, 2026-10-19); FORMSPREE_URL in Cloudflare overrides it
ap.add_argument("--formspree", default=os.environ.get("FORMSPREE_URL") or "https://formspree.io/f/xzedwyge")
ap.add_argument("--allow-placeholders", action="store_true")
a = ap.parse_args()
if a.formspree and not re.fullmatch(r"https://formspree\.io/f/[A-Za-z0-9]+", a.formspree):
    sys.exit("Formspree URL should look like https://formspree.io/f/abcd1234")

if OUT.exists():
    shutil.rmtree(OUT)
shutil.copytree(SRC, OUT, ignore=shutil.ignore_patterns("work-with-us"))
shutil.copytree(HERE / "images", OUT / "images")
sm = OUT / "sitemap.xml"
sm.write_text(re.sub(r"\s*<url>(?:(?!</url>).)*work-with-us(?:(?!</url>).)*</url>", "",
                     sm.read_text(encoding="utf-8"), flags=re.S), encoding="utf-8")

problems = []
for f in sorted(OUT.rglob("*.html")):
    s = f.read_text(encoding="utf-8")
    s = re.sub(r'\n?<div class="draft-bar".*?\n</div>\n', "\n", s, count=1, flags=re.S)
    s = re.sub(r"<html([^>]*)>", lambda m: m.group(0) if "notes-off" in m.group(1)
               else f'<html{m.group(1)} class="notes-off">', s, count=1)
    s = re.sub(r'\n?<section class="hire-band">.*?</section>\n', "\n", s, flags=re.S)
    s = re.sub(r'<li><a href="[./]*work-with-us/index\.html">[^<]*</a></li>', "", s)
    s = re.sub(r'<a href="[./]*work-with-us/index\.html">[^<]*</a>', "", s)
    s = re.sub(r'<details class="qa"><summary>Are you licensed and insured\?</summary>.*?</details>', "", s, flags=re.S)
    s = re.sub(r'\s*<a class="btn btn-quiet ph" href="#reviews"[^>]*>Review on Google</a>', "", s)  # until the Google link exists
    if a.formspree:  # every form: the quote form writes "endpoint": "", the Safe at Home list endpoint: ''
        s = re.sub(r"""(var LEADS = \{\s*"?endpoint"?\s*:\s*)(?:""|'')""", lambda m: f'{m.group(1)}"{a.formspree}"', s)
    f.write_text(s, encoding="utf-8")
    visible = re.sub(r'<[a-z]+ class="[^"]*ph-only.*?</(p|div)>', "", s, flags=re.S)
    for m in BLANKS.finditer(visible):
        problems.append(f"{f.relative_to(OUT)}: {m.group(0)[:70]}")
    if a.formspree and re.search(r"""var LEADS = \{\s*"?endpoint"?\s*:\s*(?:""|'')""", s):
        problems.append(f"{f.relative_to(OUT)}: a form is not wired to Formspree")
    if "work-with-us" in s:
        problems.append(f"{f.relative_to(OUT)}: still links to the hiring page")

print(f"Built {OUT} ({sum(1 for _ in OUT.rglob('*.html'))} pages). Form: "
      + (a.formspree or "opens an email (no --formspree given)"))
if problems:
    print("Blank placeholders still on the site:\n  " + "\n  ".join(problems))
    if not a.allow_placeholders:
        shutil.rmtree(OUT)
        sys.exit("Fill these in (or pass --allow-placeholders) before deploying.")
