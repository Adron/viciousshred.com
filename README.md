# Vicious Shred

The [viciousshred.com](https://viciousshred.com) blog: a Jekyll site that replaces the old WordPress.com site,
built and deployed to GitHub Pages by `.github/workflows/pages.yml` on every push to `main`. CloudFront serves
it at the real domain (see `infra/README.md`); migration status is in [punch-list.md](punch-list.md).

## Layout

| Path | What it is |
|------|------------|
| `posts/_posts/` | All posts. Imported WordPress posts are `.html`; new posts can be `.md`. |
| `about/`, `reactions/` | WordPress pages, re-exported by the sync script. |
| `all-posts/`, `reaction-vids/`, `reviews/`, `search-for/` | WordPress pages rebuilt as Liquid templates (paginated query loops and search don't work on static hosting). The sync script leaves them alone. |
| `wp-content/uploads/` | Images, at the same paths WordPress used. |
| `_layouts/`, `_includes/`, `assets/` | Port of the WordPress.com **Epi** theme (Automattic, GPL). Inter is self-hosted (SIL OFL). |
| `_plugins/wp_archives.rb` | Generates `/category/…/`, `/tag/…/`, `/author/adron/`, `/YYYY/MM/DD/` archives (paginated at `/page/N/` like WordPress), redirects, and `/feed/`. |
| `_data/` | Navigation, WordPress category/tag slugs. |
| `scripts/wp_export.py` | Re-runnable WordPress exporter (see below). |
| `scripts/link_check.py` | Checks the build against every WordPress URL. |
| `_wp_export/` | Raw API dump, sitemap, and image download logs (not published). |

## Writing a new post

Create `posts/_posts/YYYY-MM-DD-your-slug.md`:

```markdown
---
title: "Your Post Title"
date: 2026-11-10 09:30:00 -0800
categories: [Reaction / Review]
tags: [heavy metal, reaction]
image: /wp-content/uploads/2026/11/hero.jpg   # featured image (home page, post header, social cards)
description: "One or two sentences for the home page excerpt, search results, and social cards."
---

Post body in Markdown.
```

It's published at `https://viciousshred.com/YYYY/MM/DD/your-slug/`, the same URL pattern WordPress used
(`permalink: /:year/:month/:day/:title/` in `_config.yml`, in Pacific time). Put images under
`wp-content/uploads/YYYY/MM/` and strip location data first:
`exiftool -overwrite_original -gps:all= photo.jpg`. Existing category/tag names reuse their old WordPress
archive URLs; new ones get a slug automatically. Posts in **Reaction / Review** show up on Reaction Vids, and
posts in **Album Reviews** on Unwrapping Vinyls.

To embed a YouTube video at 16:9:

```html
<figure class="wp-block-embed is-type-video is-provider-youtube wp-block-embed-youtube wp-embed-aspect-16-9 wp-has-aspect-ratio"><div class="wp-block-embed__wrapper">
<iframe src="https://www.youtube.com/embed/VIDEO_ID" title="YouTube video player" loading="lazy" allowfullscreen></iframe>
</div></figure>
```

## Running locally

```sh
bundle install
bundle exec jekyll serve          # http://localhost:4000
```

## Re-syncing from WordPress

While the WordPress.com site is still up, this pulls any new or edited posts:

```sh
python3 -m venv .venv && .venv/bin/pip install requests beautifulsoup4 pyyaml lxml
.venv/bin/python scripts/wp_export.py all      # fetch, convert, images, optimize (needs exiftool + ImageMagick)
bundle exec jekyll build && .venv/bin/python scripts/link_check.py
```

Each step can also be run on its own: `fetch`, `convert`, `images`, `optimize`.
