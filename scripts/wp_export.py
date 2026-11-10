#!/usr/bin/env python3
"""Export viciousshred.com (WordPress.com) into this Jekyll site.

Usage:
    .venv/bin/python scripts/wp_export.py fetch     # pull raw JSON (+ sitemap) from the WP.com API
    .venv/bin/python scripts/wp_export.py convert   # raw JSON -> posts/_posts, pages, taxonomy data
    .venv/bin/python scripts/wp_export.py images    # download referenced uploads into wp-content/uploads
    .venv/bin/python scripts/wp_export.py optimize  # strip GPS EXIF, shrink oversized images in place
    .venv/bin/python scripts/wp_export.py all       # fetch + convert + images + optimize

Every step is idempotent and safe to re-run to pick up new or edited posts.
"""
import html
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse, unquote, quote

import requests
import yaml
from bs4 import BeautifulSoup, Comment

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "_wp_export" / "raw"
POSTS_DIR = ROOT / "posts" / "_posts"
UPLOADS = ROOT / "wp-content" / "uploads"
DATA_DIR = ROOT / "_data"

SITE = "viciousshred.com"  # WordPress.com site ID 55150850 (viciousshred.wordpress.com)
API = f"https://public-api.wordpress.com/wp/v2/sites/{SITE}"
DOMAIN = "viciousshred.com"

# Hosts that serve this blog's own uploads.
UPLOAD_HOSTS = {
    "viciousshred.com",
    "www.viciousshred.com",
    "viciousshred.wordpress.com",
    "viciousshred.files.wordpress.com",
}
SITE_ICON = "/wp-content/uploads/2023/11/thrashing_code_bad_skull_logo_vertical_red.png"
# Hosts whose links point at this blog.
SITE_HOSTS = {"viciousshred.com", "www.viciousshred.com", "viciousshred.wordpress.com"}

session = requests.Session()
session.headers["User-Agent"] = "viciousshred-export/1.0 (+https://viciousshred.com)"


# --------------------------------------------------------------------------- fetch

def get_all(endpoint, params):
    items, page = [], 1
    while True:
        r = session.get(f"{API}/{endpoint}", params={**params, "per_page": 100, "page": page}, timeout=60)
        if r.status_code == 400 and page > 1:  # past the last page
            break
        r.raise_for_status()
        batch = r.json()
        items.extend(batch)
        total_pages = int(r.headers.get("X-WP-TotalPages", 1))
        print(f"  {endpoint} page {page}/{total_pages} ({len(items)} items)")
        if page >= total_pages:
            break
        page += 1
        time.sleep(0.5)
    return items


def fetch():
    RAW.mkdir(parents=True, exist_ok=True)
    post_fields = ",".join([
        "id", "date", "date_gmt", "modified", "modified_gmt", "slug", "link", "status", "type",
        "title", "content", "excerpt", "categories", "tags", "featured_media", "sticky", "format",
        "jetpack_featured_media_url", "parent", "menu_order",
    ])
    data = {
        "posts": get_all("posts", {"_fields": post_fields, "orderby": "date", "order": "asc"}),
        "pages": get_all("pages", {"_fields": post_fields}),
        "categories": get_all("categories", {"_fields": "id,name,slug,count,parent,description"}),
        "tags": get_all("tags", {"_fields": "id,name,slug,count,description"}),
    }
    for name, items in data.items():
        (RAW / f"{name}.json").write_text(json.dumps(items, indent=1, ensure_ascii=False))
        print(f"wrote {len(items)} {name}")
    # The WP sitemap lists every public URL plus the images Google indexed; used for the
    # image download list and the link check.
    r = session.get(f"https://{DOMAIN}/sitemap.xml", timeout=60)
    r.raise_for_status()
    (RAW / "sitemap.xml").write_text(r.text)


# --------------------------------------------------------------------------- convert

def load(name):
    return json.loads((RAW / f"{name}.json").read_text())


def text(rendered):
    """Rendered WP title/excerpt -> plain text."""
    s = BeautifulSoup(rendered or "", "lxml").get_text(" ")
    s = html.unescape(s).replace("\xa0", " ")
    return re.sub(r"\s+", " ", s).strip()


def unwrap(url):
    """Return (host, decoded path) with WP's Photon CDN (i0.wp.com/<host>/<path>) unwrapped."""
    if url.startswith("//"):
        url = "https:" + url
    p = urlparse(url)
    host, path = p.netloc.lower(), unquote(p.path)
    if re.fullmatch(r"i\d\.wp\.com", host):
        inner_host, _, inner_path = path.lstrip("/").partition("/")
        host, path = inner_host.lower(), "/" + inner_path
    return host, path


def upload_path(url):
    """Map a WP upload URL to its local site path (/wp-content/uploads/...), or None."""
    if not url:
        return None
    host, path = unwrap(url)
    if host not in UPLOAD_HOSTS:
        return None
    if host == "viciousshred.files.wordpress.com":
        path = "/wp-content/uploads" + path
    if not path.startswith("/wp-content/uploads/"):
        return None
    return path


def site_path(url):
    """Map a link to this blog to a root-relative path, or None."""
    if url.startswith("//"):
        url = "https:" + url
    p = urlparse(url)
    if p.scheme not in ("http", "https") or p.netloc.lower() not in SITE_HOSTS:
        return None
    path = p.path or "/"
    if p.query:
        return None  # ?p=123 style links: leave untouched
    return path + (f"#{p.fragment}" if p.fragment else "")


GALLERY_SELECTORS = [
    ".wp-block-jetpack-tiled-gallery",
    "figure.wp-block-gallery",
    "div.tiled-gallery",
    "div.gallery",
]


def normalize_galleries(soup, body):
    """Replace Jetpack tiled / classic / block galleries with one simple responsive grid.

    The originals depend on WP.com CSS/JS and link thumbnails to attachment pages that
    won't exist on a static site, so each item becomes <figure><a href=original><img></a>.
    """
    for sel in GALLERY_SELECTORS:
        for gal in body.select(sel):
            if gal.parent is None:  # already replaced as part of an outer gallery
                continue
            grid = soup.new_tag("div", attrs={"class": "vs-gallery"})
            for img in gal.find_all("img"):
                full = img.get("data-orig-file") or img.get("src", "")
                caption = None
                item = img.find_parent(["figure", "li"]) or img.find_parent(class_="tiled-gallery-item")
                if item:
                    cap = item.find(class_=re.compile(r"tiled-gallery-caption|wp-caption-text|gallery-caption")) or item.find("figcaption")
                    if cap:
                        caption = cap.get_text(" ", strip=True)
                fig = soup.new_tag("figure")
                a = soup.new_tag("a", href=full)
                a.append(soup.new_tag("img", src=full, alt=img.get("alt", ""), loading="lazy"))
                fig.append(a)
                if caption:
                    fc = soup.new_tag("figcaption")
                    fc.string = caption
                    fig.append(fc)
                grid.append(fig)
            gal.replace_with(grid)


YOUTUBE_ID = re.compile(r"(?:youtube(?:-nocookie)?\.com/(?:embed/|watch\?v=|shorts/)|youtu\.be/)([A-Za-z0-9_-]{11})")


def youtube_iframe(soup, vid, title="YouTube video player"):
    return soup.new_tag("iframe", attrs={
        "loading": "lazy",
        "title": title,
        "src": f"https://www.youtube.com/embed/{vid}?rel=1",
        "allow": "accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share",
        "referrerpolicy": "strict-origin-when-cross-origin",
        "allowfullscreen": "",
    })


def responsive_embed(soup, iframe):
    """Wrap an iframe in the block-editor embed markup; the block-library CSS keeps it 16:9."""
    fig = soup.new_tag("figure", attrs={
        "class": "wp-block-embed is-type-video is-provider-youtube wp-block-embed-youtube "
                 "wp-embed-aspect-16-9 wp-has-aspect-ratio"})
    wrap = soup.new_tag("div", attrs={"class": "wp-block-embed__wrapper"})
    fig.append(wrap)
    wrap.append(iframe)
    return fig


def normalize_embeds(soup, body):
    """Clean WordPress.com's YouTube embeds into plain, responsive iframes.

    WP.com wraps them in <span class="embed-youtube"> with a sandboxed iframe carrying a
    dozen legacy player params; the figure/wrapper classes are what make them 16:9.
    """
    for iframe in body.find_all("iframe"):
        src = iframe.get("src", "")
        m = YOUTUBE_ID.search(src)
        if not m:
            continue
        clean = youtube_iframe(soup, m.group(1), iframe.get("title") or "YouTube video player")
        span = iframe.find_parent("span", class_="embed-youtube")
        if iframe.find_parent(class_="wp-block-embed__wrapper"):
            (span or iframe).replace_with(clean)
        else:
            (span or iframe).replace_with(responsive_embed(soup, clean))
    # Bare YouTube URLs left as a paragraph (oEmbed that WP rendered as a link): embed them.
    for wrapper in body.select("figure.wp-block-embed .wp-block-embed__wrapper"):
        if wrapper.find("iframe"):
            continue
        m = YOUTUBE_ID.search(wrapper.get_text(" "))
        if m:
            wrapper.clear()
            wrapper.append(youtube_iframe(soup, m.group(1)))


def clean_html(content, image_refs, known_paths=frozenset()):
    soup = BeautifulSoup(content, "lxml")
    body = soup.body or soup

    for c in body.find_all(string=lambda s: isinstance(s, Comment)):
        c.extract()
    normalize_galleries(soup, body)
    normalize_embeds(soup, body)
    # WP.com sharing/likes/related-post widgets that occasionally get rendered into content.
    for sel in ["div.sharedaddy", "div.jp-relatedposts", "div#jp-post-flair", "div.wpcnt"]:
        for el in body.select(sel):
            el.decompose()

    for img in body.find_all("img"):
        src = img.get("src", "")
        local = upload_path(src)
        if local:
            image_refs.setdefault(local, None)
            img["src"] = local
            # Static hosting can't do on-the-fly resizing; serve the original.
            for attr in ("srcset", "sizes"):
                img.attrs.pop(attr, None)
        elif src.startswith("http://"):
            img["src"] = "https://" + src[len("http://"):]
        for attr in list(img.attrs):
            if attr.startswith("data-"):
                del img[attr]

    for a in body.find_all("a", href=True):
        href = a["href"].strip()
        local = upload_path(href)
        if local:
            image_refs.setdefault(local, None)
            a["href"] = local
            continue
        local = site_path(href)
        if local:
            img = a.find("img")
            if img and local.split("#")[0] not in known_paths and img.get("src", "").startswith("/wp-content/"):
                # Image linked to a WP attachment page, which doesn't exist here: link the file itself.
                a["href"] = img["src"]
            else:
                a["href"] = local

    for tag in body.find_all(["iframe", "embed", "source", "video", "audio", "script"]):
        for attr in ("src", "data"):
            v = tag.get(attr)
            if v and v.startswith("http://"):
                tag[attr] = "https://" + v[len("http://"):]

    out = "".join(str(c) for c in body.contents)
    return re.sub(r"\n{3,}", "\n\n", out).strip() + "\n"


def front_matter(fm):
    return "---\n" + yaml.safe_dump(fm, sort_keys=False, allow_unicode=True, width=1000) + "---\n"


def wp_date(post):
    # date is site-local; date_gmt lets us compute the offset so Jekyll gets the exact instant.
    from datetime import datetime
    local = datetime.fromisoformat(post["date"])
    gmt = datetime.fromisoformat(post["date_gmt"])
    mins = int((local - gmt).total_seconds() // 60)
    sign = "+" if mins >= 0 else "-"
    mins = abs(mins)
    return f"{post['date'].replace('T', ' ')} {sign}{mins // 60:02d}{mins % 60:02d}"


# WordPress paths GitHub Pages can't deploy (4-byte UTF-8 such as emoji stalls the Pages sync).
# Built at the ASCII path; the CloudFront function 301s the original URL to it.
ASCII_PATHS = {
    "/2024/11/27/2025-releases-lining-up-already-%f0%9f%a4%98%f0%9f%8f%bb/": "/2024/11/27/2025-releases-lining-up-already/",
}


def permalink_of(link):
    p = urlparse(link)
    path = p.path if p.path.endswith("/") else p.path + "/"
    return ASCII_PATHS.get(path, path)


def sitemap_images():
    f = RAW / "sitemap.xml"
    if not f.exists():
        return []
    return [html.unescape(u) for u in re.findall(r"<image:loc>([^<]+)</image:loc>", f.read_text())]


def convert():
    posts, pages = load("posts"), load("pages")
    cats = {c["id"]: c for c in load("categories")}
    tags = {t["id"]: t for t in load("tags")}

    POSTS_DIR.mkdir(parents=True, exist_ok=True)
    image_refs = {}  # local path -> download URL (None = derive from WP uploads)
    written = set()
    known_paths = {permalink_of(p["link"]) for p in posts + pages} | {"/"}

    for p in posts:
        if p.get("status") != "publish":
            continue
        permalink = permalink_of(p["link"])
        # Filename slug must be filesystem safe; the real URL comes from `permalink`.
        file_slug = re.sub(r"[^a-z0-9-]+", "-", unquote(p["slug"]).lower()).strip("-")[:80] or str(p["id"])
        fname = f"{p['date'][:10]}-{file_slug}.html"
        featured = upload_path(p.get("jetpack_featured_media_url"))
        if featured:
            image_refs.setdefault(featured, None)
        fm = {
            "layout": "post",
            "title": text(p["title"]["rendered"]),
            "date": wp_date(p),
            "last_modified_at": p["modified_gmt"].replace("T", " ") + " +0000",
            "permalink": permalink,
            "wp_id": p["id"],
            "categories": [html.unescape(cats[c]["name"]) for c in p["categories"] if c in cats],
            "tags": [html.unescape(tags[t]["name"]) for t in p["tags"] if t in tags],
            "description": text(p["excerpt"]["rendered"]),
        }
        if featured:
            fm["image"] = featured
        if p.get("sticky"):
            fm["sticky"] = True
        # Old content may contain literal {{ }} or {% %} (there are code blocks); never run it through Liquid.
        fm["render_with_liquid"] = False
        body = clean_html(p["content"]["rendered"], image_refs, known_paths)
        (POSTS_DIR / fname).write_text(front_matter(fm) + body)
        written.add(fname)

    # Remove posts that no longer exist upstream, but only ones this script created.
    for f in POSTS_DIR.glob("*.html"):
        if f.name not in written and "wp_id:" in f.read_text()[:2000]:
            f.unlink()
            print(f"removed stale {f.name}")

    for p in pages:
        if p.get("status") != "publish":
            continue
        permalink = permalink_of(p["link"])
        out = ROOT / permalink.strip("/") / "index.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        if out.exists() and "wp_id:" not in out.read_text()[:2000]:
            print(f"kept hand-edited {out.relative_to(ROOT)}")
            continue
        fm = {
            "layout": "page",
            "title": text(p["title"]["rendered"]),
            "permalink": permalink,
            "wp_id": p["id"],
            "render_with_liquid": False,
        }
        out.write_text(front_matter(fm) + clean_html(p["content"]["rendered"], image_refs, known_paths))

    # The WordPress site icon (favicon.ico and assets/icons/ are generated from it).
    image_refs.setdefault(SITE_ICON, None)
    for url in sitemap_images():
        local = upload_path(url)
        if local:
            image_refs.setdefault(local, None)

    # Taxonomy data: exact WP slugs so /category/<slug>/ and /tag/<slug>/ keep their URLs.
    DATA_DIR.mkdir(exist_ok=True)
    taxonomy = {
        "categories": {html.unescape(c["name"]): c["slug"] for c in cats.values() if c["count"]},
        "tags": {html.unescape(t["name"]): t["slug"] for t in tags.values() if t["count"]},
    }
    (DATA_DIR / "wp_taxonomy.yml").write_text(yaml.safe_dump(taxonomy, allow_unicode=True, sort_keys=True))

    (RAW.parent / "image_refs.tsv").write_text(
        "".join(f"{k}\t{v or ''}\n" for k, v in sorted(image_refs.items())))
    print(f"wrote {len(written)} posts, {len(pages)} pages, {len(image_refs)} image refs")


# --------------------------------------------------------------------------- images

def images():
    refs = dict(line.split("\t") for line in (RAW.parent / "image_refs.tsv").read_text().splitlines())
    log = []
    todo = [r for r in refs if not (ROOT / r.lstrip("/")).exists()]
    print(f"{len(refs)} referenced, {len(todo)} to download")
    for i, path in enumerate(todo, 1):
        dest = ROOT / path.lstrip("/")
        rel = quote(path[len("/wp-content/uploads/"):])
        sources = [refs[path]] if refs[path] else [
            f"https://{DOMAIN}/wp-content/uploads/{rel}", f"https://viciousshred.files.wordpress.com/{rel}"]
        ok = False
        r = None
        for src in sources:
            try:
                # WP.com transcodes .webp uploads to JPEG/PNG unless the client accepts webp.
                accept = {"Accept": "image/webp,image/*"} if path.lower().endswith(".webp") else {}
                r = session.get(src, timeout=60, headers=accept)
            except requests.RequestException as e:
                log.append(f"{path}\terror\t{e}")
                continue
            ctype = r.headers.get("content-type", "")
            if r.ok and not ctype.startswith("text/html"):
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(r.content)
                ok = True
                break
        if not ok:
            log.append(f"{path}\tmissing\t{r.status_code if r is not None else ''}")
        if i % 50 == 0:
            print(f"  {i}/{len(todo)}")
        time.sleep(0.1)
    (RAW.parent / "image_errors.tsv").write_text("\n".join(log) + ("\n" if log else ""))
    print(f"done; {len(log)} failures logged to _wp_export/image_errors.tsv")


# --------------------------------------------------------------------------- optimize

MAX_DIM = 2000
MIN_BYTES = 1_000_000


def optimize():
    """Strip GPS EXIF from every photo, then shrink oversized images in place (same path/name,
    so URLs don't change). Needs exiftool and ImageMagick."""
    if UPLOADS.exists():
        subprocess.run(["exiftool", "-q", "-q", "-overwrite_original", "-r", "-gps:all=",
                        "-ext", "jpg", "-ext", "jpeg", "-ext", "png", "-ext", "webp", str(UPLOADS)])
    manifest = RAW.parent / "optimized.txt"
    done = set(manifest.read_text().split("\n")) if manifest.exists() else set()
    before = after = 0
    for f in sorted(UPLOADS.rglob("*")):
        rel = str(f.relative_to(ROOT))
        if f.suffix.lower() not in (".jpg", ".jpeg", ".png") or rel in done:
            continue
        done.add(rel)
        if f.stat().st_size < MIN_BYTES:
            continue
        size = f.stat().st_size
        tmp = f.with_name(f".opt-{f.name}")
        args = ["magick", str(f), "-auto-orient", "-resize", f"{MAX_DIM}x{MAX_DIM}>", "-strip"]
        if f.suffix.lower() in (".jpg", ".jpeg"):
            args += ["-sampling-factor", "4:2:0", "-quality", "82", "-interlace", "JPEG"]
        else:
            args += ["-define", "png:compression-level=9"]
        subprocess.run(args + [str(tmp)], check=True)
        if tmp.stat().st_size < size:
            tmp.replace(f)
        else:
            tmp.unlink()
        before += size
        after += f.stat().st_size
    manifest.write_text("\n".join(sorted(done)) + "\n")
    print(f"optimized: {before / 1e6:.1f} MB -> {after / 1e6:.1f} MB")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    steps = {
        "fetch": [fetch],
        "convert": [convert],
        "images": [images],
        "optimize": [optimize],
        "all": [fetch, convert, images, optimize],
    }
    for step in steps[cmd]:
        step()
