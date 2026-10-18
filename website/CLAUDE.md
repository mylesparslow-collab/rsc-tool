# CLAUDE.md: the website (rscrafters.com)

Read this first when a change touches the website. You are probably on Nick Parslow's Mac, helping him change the
site for Refined Space Crafters. Nick is 66 and not a programmer: explain in plain words, one step at a time, and do
the editing for him. Myles (his son) approves what goes live. The rules in the top-level `CLAUDE.md` still apply.

## How it goes live

Cloudflare Pages builds this folder from GitHub. The repo's default branch is the live site; every other branch
gets its own preview link.

1. Make the change on a branch (on Nick's Mac: `nick-mac-fixes-YYYY-MM-DD`, never the default branch).
2. `python3 build.py` (needs `pip install -r requirements.txt` once). It must end without errors.
3. Open the changed page: `open public/index.html` (or the page's folder). Check a narrow window too.
4. Commit and push the branch. Cloudflare posts a preview link on the branch's commit in GitHub
   (or see Workers & Pages › rscrafters › Deployments).
5. Tell Nick what changed in plain words and give him the preview link. Myles merges it to make it live.

Never push to the default branch and never publish another way (no drag-and-drop uploads, no other hosts).

## What is where

| Path | What |
|---|---|
| `base/` | The site's own pages: home `index.html`, services (`decks-and-stairs/`, `kitchens/`, `bathrooms/`, `restoration-and-built-ins/`, `bulkheads-and-outdoor/`), towns (`saratoga-springs/`, `wilton/`, `capital-region/`), `safe-at-home/`, `work-with-us/` (on hold) and `styles.css` |
| `posts/<slug>.md` | Blog posts. Each needs a row in `keyword-plan.md`. Read `WRITING-BRIEF.md` before writing one |
| `images/` | Photos: `name.jpg` plus `name-480.webp`, `name-800.webp` (and larger) copies |
| `build_blog.py` | Builds `dist/`: posts, blog index, "Guides" lists on pages, sitemap, robots.txt |
| `check_blog.py` | Fails the build on broken links and banned claims or wording |
| `make_deploy.py` | Turns `dist/` into `public/`: removes the yellow draft-notes bar, leaves out pages on hold, wires the form |
| `dist/`, `public/` | Built output. Not committed; never edit them by hand |

The header, menu and footer are repeated in every page in `base/`: a change to one (phone, hours, a menu link) must
be made in all of them (`grep -rn` first).

## On hold (Myles, 2026-10-18)

- **Hiring page** (`work-with-us/`) and every link to it are left out of the live site. Keep editing it in `base/` if
  asked, but it stays off until Myles says so (`make_deploy.py`).
- **Insurance and licensing**: say nothing about Nick's insurance or licenses anywhere. The FAQ answer is removed.
- **"Review on Google" button**: hidden until the Google Business Profile exists and Myles sends its review link.

## Rules

1. **Never invent facts.** No made-up reviews, licenses, insurance, awards, years in business, prices, warranties or
   past accessibility work. If Nick hasn't said it, leave it out. `check_blog.py` catches some of this, not all.
2. **Reviews** must be real client words, first name and town only, ideally with the client's OK. Older reviews from
   the Reclaimed Space Crafters days may be labeled "formerly Reclaimed Space Crafters".
3. **Draft notes**: text in `class="ph"` is unconfirmed; `ph-only` blocks are notes. When Nick confirms something,
   replace the text, remove the `ph` wrapper, and drop that item from the "What to confirm" list on every page.
4. **Keep name, phone and email identical everywhere.** Business name: Refined Space Crafters. Phone (518) 932-9919.
5. **Small changes.** Don't redesign, reformat, or rename pages or files. Match the surrounding HTML.
6. **Forms** open an email to Nick until Myles sets a Formspree address (`FORMSPREE_URL` in Cloudflare's build
   settings). Keep the form's field names: the RSC tool reads them (`rsc/intake.py`). No tracking or new services.
7. **Domain** is `https://rscrafters.com` (`SITE` in `build_blog.py`). Don't hard-code other domains.
