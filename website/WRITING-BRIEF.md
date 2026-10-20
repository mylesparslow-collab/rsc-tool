# Writing brief for RSC blog posts

Read this before writing or editing any post in `posts/`. The plan of posts is `keyword-plan.md`.

## The business (what we may say)

Refined Space Crafters is a design-build remodeling contractor based in Saratoga Springs, NY, serving Saratoga County
and the Capital Region (Saratoga Springs, Wilton, Ballston Spa, Malta, Greenfield, Gansevoort, Milton, Stillwater,
Mechanicville, Schuylerville, Corinth, Clifton Park, Halfmoon, Round Lake, Glens Falls, Queensbury).
Phone: (518) 932-9919, call or text.

Facts we may state:
- The same team designs and builds the project, with one point of contact.
- We visit the site first. The client receives a written scope of work organized by phase, with the price and a
  payment schedule tied to each phase.
- Any change to scope, price or schedule is agreed in writing (a change order) before the work proceeds.
- Services: decks, stairs and railings; kitchens; bathrooms; built-ins and custom carpentry; old-house restoration
  (stairs, porches, trim, ceilings); bulkhead (cellar door) replacement and cellar stairs; outdoor showers and garden
  structures; porch enclosures into finished rooms; additions; roofing, siding, soffits and gutters as part of a project.
- Work shown on the website: a full-width rear deck with sage-painted rails and black balusters; a composite deck and
  stair with black aluminum rail over a stamped concrete patio; a kitchen with sage cabinets built around an exposed
  original brick chimney; a bathroom with a white vanity and glass walk-in shower; subway-tile and accent-tile showers;
  scroll-cut porch balusters; a staircase restored with its turned newel kept; a cracked ceiling covered in tin-look
  tiles; a worn steel bulkhead replaced; a cellar stair rebuilt; office built-ins and glass French doors; a garden bridge.
- Safe at Home, our aging-in-place and home safety service (assessments, stair rails, grab bars, accessible
  bathrooms), is **in preparation**. People can join the waiting list on `/safe-at-home/`.

## Never claim (no exceptions)

- Licenses, insurance, certifications (no CAPS), awards, memberships, years in business, number of jobs, warranties,
  guarantees, response times, an office, employees or crew size.
- Prices, price ranges, rates, discounts or any dollar figure, even "typical" market costs. Talk about what drives
  cost instead.
- Testimonials, client names, reviews, quotes from customers.
- Any past aging-in-place or accessibility project. Safe at Home posts are educational and point to the waiting list.
- Nick by name. Don't mention him at all; the home page already credits him as founder.

If a sentence needs a business fact that is not in the list above, leave it out. If it truly matters, wrap it like this
and list it in the `flags:` field:
`<span class="ph" title="Confirm with Nick: why">the claim</span>`

## Home and code facts

Use well-established, conservative guidance and phrase intervals as typical ranges ("most decks need a new coat every
two to three years"). For building code, refer to the New York State Residential Code (based on the International
Residential Code) and keep to widely known provisions, for example: a handrail on stairs with four or more risers,
handrail height 34 to 38 inches; deck guards where the surface is more than 30 inches above grade, at least 36 inches
high on residential decks, with openings that a 4-inch sphere cannot pass through. Don't state local fees, frost depths,
office hours, or rules you are not sure of; say "check with your town or city building department". Exterior changes in
Saratoga Springs historic districts can need Design Review Commission approval. Pre-1978 homes can have lead paint and
older popcorn ceilings or pipe insulation can contain asbestos: recommend testing before disturbing them.

For safety-critical topics (electrical, structural, mold, asbestos, lead), tell the reader when to call a licensed
professional; don't give DIY instructions for dangerous work.

## Voice

- Company "we" voice, like an articulate, professional contractor writing for homeowners. Plain declarative sentences
  with specifics.
- No slogans or folksy lines ("good bones", "straight answers", "from first sketch to final coat", "peace of mind",
  "dream kitchen", "transform your space"). No hype words ("stunning", "nestled", "elevate", "seamless").
- No em dashes. No "Here's the thing:" or colon-led lists inside prose sentences. Bullet lists are fine where they help.
- Don't address the reader with questions in every paragraph. Don't open with "Are you...?" or "As a homeowner...".
- Mention the post's town focus naturally two or three times (title, intro, one section). No keyword stuffing.
- Write for a Capital Region homeowner: snow load, freeze-thaw, ice dams, salt, short building season, older housing
  stock in the villages and cities, newer subdivisions in Malta, Wilton, Clifton Park and Halfmoon.

## Format of a post file

File: `posts/<slug>.md`, UTF-8. Front matter between `---` lines, one `key: value` per line, no nested YAML:

```
---
slug: how-often-to-stain-a-deck-upstate-ny
title: How Often to Stain a Deck in Upstate NY
h1: How often should you stain a deck in upstate New York?
description: Most decks in the Capital Region need stain every two to three years. How to tell when yours is due, and what winter does to the finish.
summary: The interval for stain and sealer in Saratoga County weather, the water test, and when boards are past saving.
flags:
---
```

- `title`: 60 characters or fewer, contains the primary keyword; the town or "NY" where natural. No business name (the
  build adds it).
- `h1`: the on-page headline. Can be a question.
- `description`: 140 to 158 characters, plain sentence(s), contains the keyword.
- `summary`: one or two sentences for the blog index card.
- `flags`: things Nick must confirm, separated by ` ; `. Empty if none.

Body, in Markdown after the front matter:
1. An opening paragraph of two to four sentences that answers the search question directly (this is what Google
   quotes). No heading above it; the build adds the H1.
2. Four to seven `##` sections. Use `###` inside if needed. A short bulleted checklist or a small table where it helps.
3. A section titled exactly `## Frequently asked questions` with two to four `###` questions, each answered in one
   short paragraph. (The build turns this into FAQ schema.)
4. A closing paragraph of two or three sentences that says what we do for this kind of project and links the service
   page. The build appends the call-to-action box after it, so don't write your own "call us" ending.

Length: 900 to 1,400 words of body.

Links: use root paths. Service and town pages: `/decks-and-stairs/`, `/kitchens/`, `/bathrooms/`,
`/restoration-and-built-ins/`, `/bulkheads-and-outdoor/`, `/safe-at-home/`, `/saratoga-springs/`, `/wilton/`,
`/capital-region/`. Other posts: `/blog/<slug>/` using slugs from `keyword-plan.md` (any row, written or not, as long
as it is in the table). Include at least one service or town link and three to five links to other posts, placed in
sentences where they help the reader. Descriptive anchor text, never "click here".

No images in the body (the build adds the hero photo). No external links except to official public resources when
they genuinely help (for example the agency named in a funding post), written as normal Markdown links.
