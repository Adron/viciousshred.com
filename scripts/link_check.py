#!/usr/bin/env python3
"""Check the local Jekyll build (_site/) against the WordPress URLs it must keep serving.

Checks every URL and image in the WordPress sitemap (saved by `wp_export.py fetch`), every
category/tag archive and its /page/N/ pages, home pagination, feeds, plus every internal
href/src in the built HTML. Run after `bundle exec jekyll build`:

    .venv/bin/python scripts/link_check.py
"""
import html
import json
import math
import re
import sys
from pathlib import Path
from urllib.parse import urlparse, unquote

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wp_export import ASCII_PATHS  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "_site"
RAW = ROOT / "_wp_export" / "raw"
PER_PAGE = 10


def exists(path):
    path = ASCII_PATHS.get(path.lower(), path)
    f = SITE / unquote(path).lstrip("/")
    return (f / "index.html").exists() if path.endswith("/") else f.exists()


def main():
    sm = (RAW / "sitemap.xml").read_text()
    imgs = [html.unescape(u) for u in re.findall(r"<image:loc>([^<]+)</image:loc>", sm)]
    urls = [html.unescape(u) for u in re.findall(r"<loc>([^<]+)</loc>", sm) if html.unescape(u) not in imgs]
    posts = json.loads((RAW / "posts.json").read_text())
    expected = [urlparse(u).path for u in urls + imgs]
    for kind, base in (("categories", "category"), ("tags", "tag")):
        for t in json.loads((RAW / f"{kind}.json").read_text()):
            if t["count"]:
                expected.append(f"/{base}/{t['slug']}/")
                expected += [f"/{base}/{t['slug']}/page/{n}/" for n in range(2, math.ceil(t["count"] / PER_PAGE) + 1)]
    expected += [f"/page/{n}/" for n in range(2, math.ceil(len(posts) / PER_PAGE) + 1)]
    expected += ["/feed/", "/feed.xml", "/sitemap.xml", "/robots.txt", "/author/adron/"]

    missing = [p for p in expected if not exists(p)]
    broken = set()
    for f in SITE.rglob("*.html"):
        for ref in re.findall(r'(?:href|src)="(/[^"#?]*)', f.read_text(errors="ignore")):
            if not ref.startswith("//") and not exists(ref) and not (SITE / unquote(ref).lstrip("/")).exists():
                broken.add(ref)

    print(f"{len(urls)} sitemap URLs, {len(imgs)} sitemap images, {len(expected)} expected paths in total")
    print(f"missing from build: {len(missing)}")
    for p in missing:
        print("  ", p)
    print(f"broken internal links: {len(broken)}")
    for p in sorted(broken):
        print("  ", p)
    return 1 if missing or broken else 0


if __name__ == "__main__":
    sys.exit(main())
