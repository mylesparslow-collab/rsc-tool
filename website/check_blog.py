"""Checks the built blog (run after build_blog.py): broken internal links, banned claims and wording, front matter limits."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent
DIST, POSTS = ROOT / "dist", ROOT / "posts"
BANNED = [r"\$\d", "—", r"\blicensed\b(?! electrician| plumber| professional| contractor| electricians| plumbers| trade| architect| abatement| heating| HVAC| locally)",
          r"\bwe are insured\b", r"\bfully insured\b", r"\bwarrant(?!y information)", r"(?<!not )\bguarantee", r"\bCAPS\b", r"years of experience",
          r"\bstunning\b", r"\bnestled\b", r"\belevate\b", r"\bseamless", r"dream (kitchen|bath|home)", r"peace of mind",
          r"good bones", r"straight answers", r"transform your", r"\bNick\b", r"testimonial", r"award"]
problems = 0


def report(msg):
    global problems
    problems += 1
    print(msg)


for md in sorted(POSTS.glob("*.md")):
    text = md.read_text(encoding="utf-8")
    fm = dict(l.split(":", 1) for l in text.split("---")[1].strip().splitlines() if ":" in l)
    fm = {k.strip(): v.strip() for k, v in fm.items()}
    if len(fm.get("title", "")) > 60:
        report(f"{md.name}: title {len(fm['title'])} chars")
    if not 120 <= len(fm.get("description", "")) <= 160:
        report(f"{md.name}: description {len(fm.get('description', ''))} chars")
    body = text.split("---", 2)[2]
    for pat in BANNED:
        for m in re.finditer(pat, body, re.I if pat[0] != "\\" or "CAPS" not in pat else 0):
            line = body[max(0, m.start() - 60):m.end() + 60].replace("\n", " ")
            report(f"{md.name}: '{m.group(0)}' ... {line}")
    if "## Frequently asked questions" not in body:
        report(f"{md.name}: no FAQ section")
    words = len(body.split())
    if words < 800:
        report(f"{md.name}: only {words} words")

for page in DIST.rglob("*.html"):
    html = page.read_text(encoding="utf-8")
    for href in re.findall(r'href="([^"#:?]+)(?:#[^"]*)?"', html):
        if href.startswith(("http", "//", "data")) or not href:
            continue
        target = (page.parent / href).resolve()
        if "images/" in href:
            continue
        if not target.exists():
            report(f"{page.relative_to(DIST)}: broken link {href}")

print(f"{problems} problem(s)")
sys.exit(1 if problems else 0)
