"""Build the RSC blog into dist/ from posts/*.md and the website pages in base/.

    python3 build_blog.py

Reads keyword-plan.md (category, town, service link, hero image per post), renders every post in posts/ to
dist/blog/<slug>/index.html, writes dist/blog/index.html, dist/sitemap.xml and dist/robots.txt, copies the base pages
into dist/ with a "Guides" block of related posts added (between <!-- blog-guides --> markers), and appends the blog
styles to dist/styles.css. Needs the `markdown` package. Images are not copied: they already live on the site.
"""
import html
import json
import re
import shutil
import sys
from datetime import date
from pathlib import Path

import markdown

ROOT = Path(__file__).parent
BASE, POSTS, DIST = ROOT / "base", ROOT / "posts", ROOT / "dist"
SITE = "https://rscrafters.com"  # registered 2026-10-18 (Cloudflare)
NAME = "Refined Space Crafters"
PHONE, TEL = "(518) 932-9919", "+15189329919"
PUBLISHED = "2026-10-18"
NAME_PH = NAME
NEXTDOOR = "https://nextdoor.com/pages/reclaimed-space-crafters-saratoga-springs-ny/"
YELP = "https://www.yelp.com/biz/refined-space-crafters-saratoga-springs"

# name: (width, height, srcset widths, alt). Files are images/<name>.jpg and images/<name>-<w>.webp on the site.
IMAGES = {
    "porch-balusters": (1600, 1200, [480, 800, 1200, 1600], "White scroll-cut balusters on a green porch rail"),
    "newel-handrail": (1080, 1600, [480, 800, 1080], "Square wood newel with a ball cap and curved handrail"),
    "deck-rear": (1170, 837, [480, 800, 1170], "Rear of a gray house with a full-width deck, sage-painted rails and black balusters"),
    "deck-dark-a": (1600, 1200, [480, 800, 1200, 1600], "Dark-stained platform deck and steps in a wooded yard"),
    "deck-dark-b": (1600, 1200, [480, 800, 1200, 1600], "Dark-stained ground-level deck with entry steps beside a house"),
    "tub-surround": (1335, 1600, [480, 800, 1200, 1335], "White tub and shower surround"),
    "shower-accent-tile": (1170, 1549, [480, 800, 1170], "Tiled walk-in shower with diamond accent tiles and a shower panel"),
    "bath-vanity-shower": (1170, 1548, [480, 800, 1170], "Bathroom with white vanity, black mirror and fixtures, and a glass walk-in shower"),
    "window-trim": (1600, 1454, [480, 800, 1200, 1600], "Window cased in white trim with corner rosettes"),
    "bulkhead-worn": (1200, 1600, [480, 800, 1200], "Worn green bulkhead with peeling paint and leaves on the steps"),
    "bulkhead-new-open": (1600, 1200, [480, 800, 1200, 1600], "New white bulkhead with the hatch open and a glazed door below"),
    "cellar-stair-after": (1112, 1600, [480, 800, 1112], "Rebuilt cellar stairs with new treads and closed risers"),
    "composite-landing": (1200, 1600, [480, 800, 1200], "Gray composite landing with a black border and aluminum rail outside French doors"),
    "composite-stair": (1512, 2016, [480, 800, 1200, 1512], "Composite deck steps with black aluminum rail above a stamped concrete patio"),
    "composite-detail": (1600, 1200, [480, 800, 1200, 1600], "Close view of gray composite boards, dark border and black aluminum balusters"),
    "composite-steps-white": (1600, 1508, [480, 800, 1200, 1600], "Composite stairs with white risers and black rail beside a stamped concrete patio"),
    "ceiling-before": (1090, 614, [480, 800, 1090], "Cracked textured ceiling before the work"),
    "ceiling-after": (1600, 1033, [480, 800, 1200, 1600], "Copper-tone tin-look ceiling tiles with a branch light fixture"),
    "kitchen-brick": (1170, 861, [480, 800, 1170], "Kitchen with sage green cabinets, white counters, stainless appliances and an exposed brick chimney"),
    "kitchen-render": (1350, 631, [480, 800, 1200, 1350], "Design render of a kitchen with white cabinets and a wood island"),
    "vanity-fluted": (1600, 1195, [480, 800, 1200, 1600], "White vanity with fluted trim and two faucets"),
    "vintage-bath": (1154, 1520, [480, 800, 1154], "Bathroom with green beadboard, floral wallpaper and vintage pastel fixtures"),
    "stair-white-pt": (898, 1088, [480, 800, 898], "White vinyl deck rail with new pressure-treated stair treads"),
    "stair-blue": (1170, 1552, [480, 800, 1170], "Deck staircase painted powder blue with black metal balusters"),
    "stair-dark": (1354, 1600, [480, 800, 1200, 1354], "Dark-stained entry steps with matching rails"),
    "stair-restored-a": (1211, 1600, [480, 800, 1200, 1211], "Staircase with white risers and a dark turned newel post"),
    "stair-restored-b": (1174, 1600, [480, 800, 1174], "Staircase with painted treads and a turned newel post"),
    "handrail-landing": (640, 882, [480, 640], "Wood handrail and balusters at a stair landing"),
    "office-built-in": (1600, 1200, [480, 800, 1200, 1600], "Built-in wood bookcase and credenza"),
    "office-french-doors": (1192, 1600, [480, 800, 1192], "Wood-framed French doors with transom windows"),
    "shower-barn-door": (1200, 1600, [480, 800, 1200], "Wood outdoor shower enclosure with a sliding barn door"),
    "bridge-wide": (2040, 1530, [480, 800, 1200, 1600, 2040], "Curved red wood footbridge over a backyard pond"),
    "bench-lift-top": (1600, 1377, [480, 800, 1200, 1600], "Wood storage bench with two lift-top lids open"),
}

CATEGORIES = ["Repair timing", "Decks and outdoor", "Kitchens and baths", "Old houses", "Town guides",
              "Hiring a contractor", "Safe at Home"]
CAT_BLURB = {
    "Repair timing": "How often things need attention in a Capital Region house, and the signs that a repair can't wait.",
    "Decks and outdoor": "Decks, porches, stairs and outdoor structures built for snow, salt and freeze-thaw.",
    "Kitchens and baths": "Planning a kitchen or bathroom remodel: order of work, timing and what drives cost.",
    "Old houses": "Repairing and restoring older homes: stairs, trim, porches and built-ins.",
    "Town guides": "Notes on the housing and common projects in the towns we serve.",
    "Hiring a contractor": "What a homeowner should expect from any contractor before, during and after a job.",
    "Safe at Home": "Aging in place: making a home safer for the years ahead. Our Safe at Home service is in preparation.",
}
SERVICE_NAMES = {
    "/decks-and-stairs/": "Decks and stairs", "/kitchens/": "Kitchens", "/bathrooms/": "Bathrooms",
    "/restoration-and-built-ins/": "Restoration and built-ins", "/bulkheads-and-outdoor/": "Bulkheads and outdoor projects",
    "/safe-at-home/": "Safe at Home", "/saratoga-springs/": "Saratoga Springs", "/wilton/": "Wilton",
    "/capital-region/": "the Capital Region",
}
CTA = {  # call-to-action box per service link: (heading, sentence)
    "/decks-and-stairs/": ("Planning a deck, stair or railing?", "Tell us about the deck or stairs and what isn’t working."),
    "/kitchens/": ("Planning a kitchen remodel?", "Tell us about your kitchen and how you use it."),
    "/bathrooms/": ("Planning a bathroom project?", "Tell us about the bathroom and what you would like to change."),
    "/restoration-and-built-ins/": ("Repairing or restoring part of your house?", "Tell us what needs repair, or what you would like built."),
    "/bulkheads-and-outdoor/": ("Need a bulkhead, cellar stair or outdoor project?", "Tell us what needs replacing or building."),
    "/capital-region/": ("Planning a project in your town?", "Tell us about the house and the project."),
}
FOLLOW_UP = "We will follow up to discuss it and schedule a site visit."


def esc(s: str) -> str:
    return html.escape(s, quote=True)


def read_plan():
    plan = {}
    for line in (ROOT / "keyword-plan.md").read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 9 and cells[0].isdigit():
            n, slug, kw, cat, town, svc, img, expl, status = cells
            plan[slug] = dict(n=int(n), slug=slug, keyword=kw, category=cat, town=town, service=svc, image=img,
                              explainer=expl, status=status)
    return plan


def read_post(path: Path, plan):
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", text, re.S)
    if not m:
        raise ValueError(f"{path.name}: no front matter")
    meta = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    meta["body"] = m.group(2).strip()
    slug = meta.get("slug") or path.stem
    if slug not in plan:
        raise ValueError(f"{path.name}: slug {slug!r} is not in keyword-plan.md")
    meta.update({k: v for k, v in plan[slug].items() if k not in meta or not meta[k]})
    meta["slug"] = slug
    meta["flags"] = [f.strip() for f in meta.get("flags", "").split(";") if f.strip()]
    for key in ("title", "h1", "description", "summary"):
        if not meta.get(key):
            raise ValueError(f"{path.name}: missing {key}")
    if meta["image"] not in IMAGES:
        raise ValueError(f"{path.name}: unknown image {meta['image']!r}")
    return meta


def rel_links(body_html: str, up: str) -> str:
    """Turn root links (/kitchens/, /blog/x/) into relative file links that work in preview and on a host."""
    def fix(m):
        href = m.group(1)
        if href.startswith("/") and not href.startswith("//"):
            path, _, frag = href[1:].partition("#")
            if path and not path.endswith("/") and "." not in path.split("/")[-1]:
                path += "/"
            target = up + (path + "index.html" if path.endswith("/") or not path else path)
            return f'href="{target}{"#" + frag if frag else ""}"'
        if href.startswith("http"):
            return f'href="{href}" target="_blank" rel="noopener"'
        return m.group(0)
    return re.sub(r'href="([^"]+)"', fix, body_html)


def split_faq(body_md: str):
    """Return (questions) from the '## Frequently asked questions' section for FAQ schema."""
    m = re.search(r"^## Frequently asked questions\s*$(.*?)(?=^## |\Z)", body_md, re.M | re.S)
    if not m:
        return []
    faqs = []
    for q in re.finditer(r"^### (.+?)\s*$(.*?)(?=^### |\Z)", m.group(1), re.M | re.S):
        answer = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", q.group(2)).strip()
        answer = re.sub(r"<[^>]+>", "", answer)
        answer = re.sub(r"[*_`]", "", answer)
        faqs.append((q.group(1).strip(), " ".join(answer.split())))
    return faqs


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def img_tag(name: str, up: str, sizes: str, lazy: bool = True, alt: str | None = None) -> str:
    w, h, widths, default_alt = IMAGES[name]
    srcset = ", ".join(f"{up}images/{name}-{x}.webp {x}w" for x in widths)
    load = 'loading="lazy"' if lazy else 'fetchpriority="high"'
    return (f'<img src="{up}images/{name}.jpg" srcset="{srcset}" sizes="{sizes}" width="{w}" height="{h}" '
            f'alt="{esc(alt or default_alt)}" decoding="async" {load}>')


def nice_date(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d.strftime('%B')} {d.day}, {d.year}"


def draft_bar() -> str:
    src = (BASE / "kitchens" / "index.html").read_text(encoding="utf-8")
    return ''  # draft notes removed 2026-10-19: the site is public


def chrome_top(up: str, title: str, head_extra: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{esc(title)}</title>
{head_extra}
<meta name="robots" content="index, follow, max-image-preview:large">
<meta name="theme-color" content="#F5F6F3">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' fill='%231C2420'/%3E%3Ctext x='32' y='45' text-anchor='middle' font-family='Georgia,serif' font-size='40' fill='%23F5F6F3'%3ER%3C/text%3E%3Crect x='14' y='51' width='36' height='3' fill='%238C2F22'/%3E%3C/svg%3E">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Libre+Caslon+Display&family=Libre+Franklin:wght@400;500;600&display=swap">
<link rel="stylesheet" href="{up}styles.css">
<script>try{{if(localStorage.getItem('rsc-notes-off')==='1')document.documentElement.classList.add('notes-off')}}catch(e){{}}</script>
"""


def chrome_header(up: str) -> str:
    nav = (f'<a href="{up}#work">Work</a><a href="{up}#services">Services</a><a href="{up}#about">About</a>'
           f'<a href="{up}safe-at-home/index.html">Safe at Home</a>'
           f'<a href="{up}blog/index.html" aria-current="page">Blog</a><a href="{up}work-with-us/index.html">Hiring</a>')
    return f"""</head>
<body>
<a class="skip" href="#main">Skip to content</a>

{draft_bar()}
<header class="site-head">
  <div class="container head-in">
    <a class="mark" href="{up}index.html" aria-label="{NAME} home">
      <span class="mark-name">{NAME_PH}</span>
      <span class="mark-sub">Design and build in Saratoga Springs, NY</span>
    </a>
    <nav class="nav" aria-label="Main">{nav}</nav>
    <div class="head-cta">
      <a class="head-tel" href="tel:{TEL}">{PHONE}</a>
      <a class="btn btn-primary" href="{up}#contact">Get a quote</a>
    </div>
    <button class="menu-btn" type="button" aria-expanded="false" aria-controls="menu">Menu</button>
  </div>
</header>

<div class="menu" id="menu" hidden>
  <div class="menu-top"><span class="mark-name">{NAME}</span><button class="menu-close" id="menuClose" type="button">Close</button></div>
  <nav aria-label="Menu"><a href="{up}index.html">Home</a>{nav.replace(' aria-current="page"', '')}<a href="{up}#faq">FAQ</a><a href="{up}#contact">Get a quote</a></nav>
  <div class="menu-foot">
    <a class="tel" href="tel:{TEL}">{PHONE}</a>
    <a class="btn btn-primary" href="{up}#contact">Get a quote</a>
  </div>
</div>
"""


def chrome_footer(up: str) -> str:
    return f"""<footer class="foot">
  <div class="container">
    <p class="foot-mark">{NAME_PH}</p>
    <div class="foot-grid">
      <div><h3>Contact</h3><p><a href="tel:{TEL}">{PHONE}</a><br>Call or text<br>Saratoga Springs, NY</p></div>
      <div><h3>Services</h3><ul><li><a href="{up}decks-and-stairs/index.html">Decks + stairs</a></li><li><a href="{up}kitchens/index.html">Kitchens</a></li><li><a href="{up}bathrooms/index.html">Bathrooms</a></li><li><a href="{up}restoration-and-built-ins/index.html">Restoration + built-ins</a></li><li><a href="{up}bulkheads-and-outdoor/index.html">Bulkheads + outdoor jobs</a></li><li><a href="{up}safe-at-home/index.html">Safe at Home (coming soon)</a></li></ul></div>
      <div><h3>Where we work</h3><ul><li><a href="{up}saratoga-springs/index.html">Saratoga Springs</a></li><li><a href="{up}wilton/index.html">Wilton</a></li><li><a href="{up}capital-region/index.html">Capital Region</a></li></ul></div>
      <div><h3>More</h3><ul><li><a href="{up}#work">Work</a></li><li><a href="{up}#faq">FAQ</a></li><li><a href="{up}blog/index.html">Blog</a></li><li><a href="{up}work-with-us/index.html">Work with us</a></li><li><a href="{NEXTDOOR}" target="_blank" rel="noopener">Nextdoor</a></li><li><a href="{YELP}" target="_blank" rel="noopener">Yelp</a></li></ul></div>
    </div>
    <p class="foot-legal">© <span id="yr">2026</span> {NAME}. Design and build across Saratoga County and the Capital Region.</p>
  </div>
</footer>

<nav class="mbar" id="mbar" aria-label="Quick contact">
  <a href="tel:{TEL}">Call us</a>
  <a class="mbar-primary" href="{up}#contact">Get a quote</a>
</nav>

<script>
(function () {{
  var menu = document.getElementById('menu'), btn = document.querySelector('.menu-btn'), head = document.querySelector('.site-head'), bar = document.getElementById('mbar');
  document.getElementById('yr').textContent = new Date().getFullYear();
  function setMenu(open) {{ menu.hidden = !open; btn.setAttribute('aria-expanded', String(open)); document.documentElement.classList.toggle('no-scroll', open); if (open) document.getElementById('menuClose').focus(); else btn.focus({{ preventScroll: true }}); }}
  btn.addEventListener('click', function () {{ setMenu(true); }});
  document.getElementById('menuClose').addEventListener('click', function () {{ setMenu(false); }});
  menu.querySelectorAll('a').forEach(function (a) {{ a.addEventListener('click', function () {{ setMenu(false); }}); }});
  document.addEventListener('keydown', function (e) {{ if (e.key === 'Escape' && !menu.hidden) setMenu(false); }});
  function onScroll() {{ head.classList.toggle('is-scrolled', window.scrollY > 8); bar.classList.toggle('is-on', window.scrollY > window.innerHeight * 0.6); }}
  window.addEventListener('scroll', onScroll, {{ passive: true }}); onScroll();
  document.addEventListener('click', function (e) {{ var a = e.target.closest && e.target.closest('a[href^="tel:"], a[href^="sms:"]'); if (a && window.gtag) window.gtag('event', a.getAttribute('href').indexOf('tel:') === 0 ? 'phone_click' : 'text_click'); }});
  var chips = document.querySelectorAll('[data-cat-filter]');
  chips.forEach(function (c) {{ c.addEventListener('click', function () {{
    var f = c.getAttribute('data-cat-filter');
    chips.forEach(function (x) {{ x.setAttribute('aria-pressed', String(x === c)); }});
    document.querySelectorAll('.blog-sec').forEach(function (s) {{ s.hidden = f !== 'all' && s.id !== f; }});
  }}); }});
}})();
</script>
<script>
(function () {{
  var h = document.documentElement, b = document.getElementById('draftToggle'), k = 'rsc-notes-off';
  if (!b) return;
  function label() {{ b.textContent = h.classList.contains('notes-off') ? 'Show draft notes' : 'Hide draft notes'; }}
  label();
  b.addEventListener('click', function () {{
    h.classList.toggle('notes-off');
    try {{ localStorage.setItem(k, h.classList.contains('notes-off') ? '1' : '0'); }} catch (e) {{}}
    label();
  }});
}})();
</script>
</body>
</html>
"""


def business_node(towns):
    area = [{"@type": "City", "name": f"{t.strip()}, NY"} for t in re.split(r",| and ", towns) if t.strip()
            and "County" not in t and "Region" not in t]
    area += [{"@type": "AdministrativeArea", "name": "Saratoga County, NY"},
             {"@type": "AdministrativeArea", "name": "Capital Region, NY"}]
    return {"@type": ["GeneralContractor", "HomeAndConstructionBusiness"], "@id": f"{SITE}/#business", "name": NAME,
            "url": f"{SITE}/", "telephone": "+1-518-932-9919", "image": f"{SITE}/images/deck-rear.jpg",
            "address": {"@type": "PostalAddress", "addressLocality": "Saratoga Springs", "addressRegion": "NY",
                        "addressCountry": "US"},
            "areaServed": area}


def card(p, up: str, heading: str = "h3") -> str:
    return (f'<a class="bcard" href="{up}blog/{p["slug"]}/index.html"><span class="bcard-img">'
            f'{img_tag(p["image"], up, "(max-width: 640px) 100vw, (max-width: 1024px) 50vw, 33vw")}</span>'
            f'<span class="bcard-cat">{esc(p["category"])}</span><{heading}>{esc(p["h1"])}</{heading}>'
            f'<p>{esc(p["summary"])}</p></a>')


def related(post, posts, n=3):
    same = [p for p in posts if p["slug"] != post["slug"] and p["category"] == post["category"]]
    svc = [p for p in posts if p["slug"] != post["slug"] and p["service"] == post["service"] and p not in same]
    rest = [p for p in posts if p["slug"] != post["slug"] and p not in same and p not in svc]
    linked = set(re.findall(r"/blog/([a-z0-9-]+)/", post["body"]))
    pool = sorted(same + svc, key=lambda p: (p["slug"] in linked, p["n"])) + rest
    return pool[:n]


def render_post(post, posts) -> str:
    up = "../../"
    url = f"{SITE}/blog/{post['slug']}/"
    md = markdown.Markdown(extensions=["tables", "toc", "sane_lists"], extension_configs={"toc": {"slugify": lambda v, s: slugify(v)}})
    body_html = rel_links(md.convert(post["body"]), up)
    toc = [(t["id"], t["name"]) for t in md.toc_tokens]
    words = len(re.sub(r"<[^>]+>", " ", body_html).split())
    minutes = max(3, round(words / 230))
    faqs = split_faq(post["body"])
    title = f"{post['title']} | {NAME}"
    img = f"{SITE}/images/{post['image']}.jpg"
    graph = [
        {"@type": "BlogPosting", "@id": f"{url}#article", "headline": post["h1"], "name": post["title"],
         "description": post["description"], "image": img, "datePublished": PUBLISHED, "dateModified": PUBLISHED,
         "author": {"@id": f"{SITE}/#business"}, "publisher": {"@id": f"{SITE}/#business"},
         "mainEntityOfPage": url, "url": url, "articleSection": post["category"], "keywords": post["keyword"],
         "wordCount": words, "inLanguage": "en-US", "isPartOf": {"@id": f"{SITE}/blog/#blog"},
         "about": {"@type": "Thing", "name": post["keyword"]},
         "spatialCoverage": {"@type": "Place", "name": f"{post['town']}, NY" if "NY" not in post["town"] else post["town"]}},
        {"@type": "BreadcrumbList", "@id": f"{url}#breadcrumb", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": f"{SITE}/"},
            {"@type": "ListItem", "position": 2, "name": "Blog", "item": f"{SITE}/blog/"},
            {"@type": "ListItem", "position": 3, "name": post["h1"], "item": url}]},
        business_node(post["town"]),
    ]
    if faqs:
        graph.append({"@type": "FAQPage", "@id": f"{url}#faq", "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faqs]})
    head = (f'<meta name="description" content="{esc(post["description"])}">\n'
            f'<link rel="canonical" href="{url}">\n'
            f'<meta property="og:site_name" content="{NAME}">\n<meta property="og:type" content="article">\n'
            f'<meta property="og:title" content="{esc(post["h1"])}">\n'
            f'<meta property="og:description" content="{esc(post["description"])}">\n'
            f'<meta property="og:url" content="{url}">\n<meta property="og:image" content="{img}">\n'
            f'<meta property="og:locale" content="en_US">\n<meta property="article:published_time" content="{PUBLISHED}">\n'
            f'<meta property="article:section" content="{esc(post["category"])}">\n'
            f'<meta name="twitter:card" content="summary_large_image">\n'
            f'<script type="application/ld+json">\n{json.dumps({"@context": "https://schema.org", "@graph": graph}, indent=1, ensure_ascii=False)}\n</script>')
    svc = post["service"]
    if svc == "/safe-at-home/":
        cta_h, cta_p = "Join the Safe at Home waiting list.", (
            "Safe at Home, our home safety and accessibility service, is in preparation. Leave your name on the "
            "waiting list and tell us about the house. " + FOLLOW_UP)
        cta_btn = f'<a class="btn btn-primary" href="{up}safe-at-home/index.html#contact">Join the waiting list</a>'
    else:
        h, p = CTA.get(svc, ("Planning a project?", "Tell us about the house and the project."))
        cta_h, cta_p = h, f"{p} {FOLLOW_UP}"
        cta_btn = f'<a class="btn btn-primary" href="{up}#contact">Request an estimate</a>'
    flags = "".join(f"<li>{esc(f)}</li>" for f in post["flags"])
    flag_note = (f'<div class="ph-note ph-only"><b>Draft note for Nick:</b> confirm before launch.<ul>{flags}</ul></div>'
                 if flags else "")
    toc_html = "".join(f'<li><a href="#{i}">{esc(n)}</a></li>' for i, n in toc)
    svc_name = SERVICE_NAMES.get(svc, "Our services")
    rel = "".join(card(p, up) for p in related(post, posts))
    out = chrome_top(up, title, head) + chrome_header(up) + f"""
<main id="main">
  <nav class="container crumbs" aria-label="Breadcrumb"><ol><li><a href="{up}index.html">Home</a></li><li><a href="{up}blog/index.html">Blog</a></li><li aria-current="page">{esc(post["category"])}</li></ol></nav>

  <article class="post" aria-labelledby="post-h">
    <header class="container post-head">
      <div>
        <a class="post-cat" href="{up}blog/index.html#{slugify(post["category"])}">{esc(post["category"])}</a>
        <h1 id="post-h">{esc(post["h1"])}</h1>
        <p class="lede">{esc(post["summary"])}</p>
        <p class="post-meta">{NAME} · Saratoga Springs, NY · <time datetime="{PUBLISHED}">{nice_date(PUBLISHED)}</time> · {minutes} min read</p>
      </div>
      <figure class="post-img">{img_tag(post["image"], up, "(max-width: 900px) 100vw, 50vw", lazy=False)}</figure>
    </header>

    <div class="container post-grid">
      <div class="post-body">
        {flag_note}
        {body_html}
      </div>
      <aside class="post-side" aria-label="On this page">
        <div class="side-box">
          <h2>On this page</h2>
          <ol class="side-toc">{toc_html}</ol>
        </div>
        <div class="side-box side-cta">
          <h2>{esc(cta_h)}</h2>
          <p>Call or text <a href="tel:{TEL}">{PHONE}</a>, or send a line about the project.</p>
          {cta_btn}
          <p class="side-link"><a href="{up}{svc.strip('/')}/index.html">{esc(svc_name)} →</a></p>
        </div>
      </aside>
    </div>
  </article>

  <section class="contact post-cta">
    <div class="container contact-in">
      <div class="contact-copy">
        <h2>{esc(cta_h)}</h2>
        <p>{esc(cta_p)}</p>
        <a class="big-tel" href="tel:{TEL}">{PHONE}</a>
        <p class="contact-note">Calls and texts reach us directly.</p>
      </div>
      <div class="sub-cta">
        <p>You can also send the details through the form on our home page.</p>
        {cta_btn}
        <h3>Related services</h3>
        <ul><li><a href="{up}{svc.strip('/')}/index.html">{esc(svc_name)}</a></li><li><a href="{up}saratoga-springs/index.html">Remodeling in Saratoga Springs</a></li><li><a href="{up}wilton/index.html">Remodeling in Wilton</a></li><li><a href="{up}capital-region/index.html">Working in the Capital Region</a></li></ul>
      </div>
    </div>
  </section>

  <section class="container post-rel" aria-labelledby="rel-h">
    <div class="sec-head"><h2 id="rel-h">Keep reading</h2><p><a class="text-link" href="{up}blog/index.html">All articles</a></p></div>
    <div class="bcards">{rel}</div>
  </section>
</main>

""" + chrome_footer(up)
    return out


def render_index(posts) -> str:
    up = "../"
    url = f"{SITE}/blog/"
    title = f"Home Repair and Remodeling Guides for Saratoga County | {NAME}"
    desc = ("Guides from a Saratoga Springs design-build contractor on repair timing, decks, kitchens, bathrooms, old "
            "houses and aging in place across the Capital Region.")
    graph = [
        {"@type": "Blog", "@id": f"{url}#blog", "url": url, "name": f"{NAME} blog", "description": desc,
         "publisher": {"@id": f"{SITE}/#business"}, "inLanguage": "en-US",
         "blogPost": [{"@type": "BlogPosting", "headline": p["h1"], "url": f"{url}{p['slug']}/",
                       "datePublished": PUBLISHED} for p in posts]},
        {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": f"{SITE}/"},
            {"@type": "ListItem", "position": 2, "name": "Blog", "item": url}]},
        business_node("Saratoga Springs, Wilton, Ballston Spa, Malta, Clifton Park, Halfmoon, Glens Falls, Queensbury"),
    ]
    head = (f'<meta name="description" content="{esc(desc)}">\n<link rel="canonical" href="{url}">\n'
            f'<meta property="og:site_name" content="{NAME}">\n<meta property="og:type" content="website">\n'
            f'<meta property="og:title" content="{esc(title)}">\n<meta property="og:description" content="{esc(desc)}">\n'
            f'<meta property="og:url" content="{url}">\n<meta property="og:image" content="{SITE}/images/porch-balusters.jpg">\n'
            f'<meta name="twitter:card" content="summary_large_image">\n'
            f'<script type="application/ld+json">\n{json.dumps({"@context": "https://schema.org", "@graph": graph}, indent=1, ensure_ascii=False)}\n</script>')
    cats = [c for c in CATEGORIES if any(p["category"] == c for p in posts)]
    chips = '<button type="button" class="chip" data-cat-filter="all" aria-pressed="true">All articles</button>' + "".join(
        f'<button type="button" class="chip" data-cat-filter="{slugify(c)}" aria-pressed="false">{esc(c)}</button>' for c in cats)
    secs = ""
    for c in cats:
        cards = "".join(card(p, up) for p in posts if p["category"] == c)
        secs += (f'<section class="blog-sec" id="{slugify(c)}" aria-labelledby="h-{slugify(c)}"><div class="sec-head">'
                 f'<h2 id="h-{slugify(c)}">{esc(c)}</h2><p>{esc(CAT_BLURB[c])}</p></div><div class="bcards">{cards}</div></section>')
    hubs = [p for p in posts if p["slug"] in ("home-maintenance-schedule-saratoga-county", "aging-in-place-saratoga-county")]
    hub_html = "".join(f'<li><a href="{p["slug"]}/index.html">{esc(p["h1"])}</a></li>' for p in hubs)
    return chrome_top(up, title, head) + chrome_header(up) + f"""
<main id="main">
  <nav class="container crumbs" aria-label="Breadcrumb"><ol><li><a href="{up}index.html">Home</a></li><li aria-current="page">Blog</li></ol></nav>

  <section class="container blog-hero">
    <div>
      <h1>Home repair and remodeling guides for Saratoga County</h1>
      <p class="lede">When things need attention in a Capital Region house, how projects are planned and built, and what to ask before you hire. Written by the design-build team at {NAME} in Saratoga Springs.</p>
    </div>
    <div class="blog-start">
      <h2>Start here</h2>
      <ul>{hub_html}</ul>
    </div>
  </section>

  <div class="container">
    <div class="chips blog-chips" role="group" aria-label="Filter articles by topic">{chips}</div>
    {secs}
  </div>

  <section class="contact">
    <div class="container contact-in">
      <div class="contact-copy">
        <h2>Have a project in mind?</h2>
        <p>Tell us about the house and what you would like done. {FOLLOW_UP}</p>
        <a class="big-tel" href="tel:{TEL}">{PHONE}</a>
        <p class="contact-note">Calls and texts reach us directly.</p>
      </div>
      <div class="sub-cta">
        <p>You can also request an estimate using the form on our home page.</p>
        <a class="btn btn-primary" href="{up}#contact">Open the quote form</a>
        <h3>Services</h3>
        <ul><li><a href="{up}decks-and-stairs/index.html">Decks and stairs</a></li><li><a href="{up}kitchens/index.html">Kitchens</a></li><li><a href="{up}bathrooms/index.html">Bathrooms</a></li><li><a href="{up}restoration-and-built-ins/index.html">Restoration and built-ins</a></li><li><a href="{up}bulkheads-and-outdoor/index.html">Bulkheads and outdoor projects</a></li><li><a href="{up}safe-at-home/index.html">Safe at Home (coming soon)</a></li></ul>
      </div>
    </div>
  </section>
</main>

""" + chrome_footer(up)


def guides_block(posts, up: str, heading: str) -> str:
    items = "".join(f'<li><a href="{up}blog/{p["slug"]}/index.html">{esc(p["h1"])}</a></li>' for p in posts)
    return (f'<!-- blog-guides -->\n  <section class="container guides" aria-labelledby="guides-h"><div class="sec-head">'
            f'<h2 id="guides-h">{esc(heading)}</h2><p><a class="text-link" href="{up}blog/index.html">All guides</a></p></div>'
            f'<ul class="guide-list">{items}</ul></section>\n  <!-- /blog-guides -->')


def inject_guides(page_html: str, block: str, before: str) -> str:
    page_html = re.sub(r"<!-- blog-guides -->.*?<!-- /blog-guides -->\s*", "", page_html, flags=re.S)
    i = page_html.find(before)
    if i < 0:
        raise ValueError(f"marker {before!r} not found")
    return page_html[:i] + block + "\n\n  " + page_html[i:]


def main():
    plan = read_plan()
    posts = sorted((read_post(p, plan) for p in POSTS.glob("*.md")), key=lambda p: p["n"])
    if DIST.exists():
        shutil.rmtree(DIST)
    (DIST / "blog").mkdir(parents=True)

    for post in posts:
        d = DIST / "blog" / post["slug"]
        d.mkdir()
        (d / "index.html").write_text(render_post(post, posts), encoding="utf-8")
    (DIST / "blog" / "index.html").write_text(render_index(posts), encoding="utf-8")

    # base pages with related guides
    for src in [BASE / "index.html", *sorted(BASE.glob("*/index.html"))]:
        rel = src.relative_to(BASE)
        page = src.read_text(encoding="utf-8")
        if rel.parts[0] == "index.html":
            picks = [p for p in posts if p["slug"] in (
                "home-maintenance-schedule-saratoga-county", "when-do-stairs-need-a-handrail",
                "kitchen-remodel-saratoga-springs-guide", "bathroom-remodel-saratoga-springs-guide",
                "what-a-remodeling-estimate-should-include", "aging-in-place-saratoga-county")]
            page = inject_guides(page, guides_block(picks, "", "Guides for homeowners"), '<section class="faq" id="faq">')
        else:
            path = "/" + rel.parts[0] + "/"
            if path == "/work-with-us/":
                picks = []
            elif path in ("/saratoga-springs/", "/wilton/"):
                town = "Saratoga Springs" if path == "/saratoga-springs/" else "Wilton"
                picks = [p for p in posts if town in p["town"]][:8]
            elif path == "/capital-region/":
                picks = [p for p in posts if p["category"] == "Town guides" and p["service"] == "/capital-region/"]
                picks += [p for p in posts if p["category"] == "Town guides" and p not in picks][:8 - len(picks)]
            else:
                picks = [p for p in posts if p["service"] == path][:8]
            if picks:
                page = inject_guides(page, guides_block(picks, "../", "Guides and articles"),
                                     '<section class="contact')
        out = DIST / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(page, encoding="utf-8")

    css = (BASE / "styles.css").read_text(encoding="utf-8")
    css = re.sub(r"/\* blog styles \*/.*", "", css, flags=re.S).rstrip() + "\n\n" + (ROOT / "blog.css").read_text(encoding="utf-8")
    (DIST / "styles.css").write_text(css, encoding="utf-8")

    pages = ["", "decks-and-stairs/", "kitchens/", "bathrooms/", "restoration-and-built-ins/", "bulkheads-and-outdoor/",
             "safe-at-home/", "saratoga-springs/", "wilton/", "capital-region/", "work-with-us/", "blog/"]
    urls = [(f"{SITE}/{p}", "2026-10-18") for p in pages] + [(f"{SITE}/blog/{p['slug']}/", PUBLISHED) for p in posts]
    sitemap = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    sitemap += [f"  <url><loc>{u}</loc><lastmod>{d}</lastmod></url>" for u, d in urls]
    sitemap.append("</urlset>")
    (DIST / "sitemap.xml").write_text("\n".join(sitemap) + "\n", encoding="utf-8")
    (DIST / "robots.txt").write_text(f"User-agent: *\nAllow: /\n\nSitemap: {SITE}/sitemap.xml\n", encoding="utf-8")
    print(f"built {len(posts)} posts into {DIST}", file=sys.stderr)


if __name__ == "__main__":
    main()
