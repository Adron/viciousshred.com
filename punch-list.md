# Migration Punch List

Running checklist for moving viciousshred.com from WordPress.com to GitHub Pages behind CloudFront, with DNS
in Route 53, email forwarding on AWS SES, and the registration transferred to Route 53 Domains. Same
pattern as transitsleuth.com.

Facts (checked 2026-11-10): registrar Automattic (WordPress.com), registry expiry 2027-07-10,
`clientTransferProhibited`, DNSSEC unsigned. Nameservers `ns1-3.wordpress.com`. Apex A `192.0.78.24/25`,
`www` CNAME → apex. **MX `0 smtp-fwd.wordpress.com`** (WordPress email forwarding is in use). WordPress
sends HSTS (`max-age=31536000`), which is why the site goes behind CloudFront + ACM rather than straight to
GitHub Pages. Site ID 55150850, theme **Epi** (WordPress.com), 8 email subscribers.

## 1. Export content
- [x] Export all 228 posts (2011-09-18 → 2024-12-25) and 6 pages (`/about/`, `/all-posts/`,
      `/reaction-vids/`, `/reviews/`, `/reactions/`, `/search-for/`) from the WordPress.com API (`scripts/wp_export.py`)
- [x] Keep exact WordPress permalinks (`/YYYY/MM/DD/slug/`), dates with the original UTC offsets
- [x] Download all 280 uploads (sitemap images, in-content images, featured images, site icon) to
      `/wp-content/uploads/` at the original paths, 0 failures; GPS EXIF stripped; images over 1 MB capped at
      2000px and recompressed (157 → 79 MB for those; uploads total 137 MB). `.webp` files fetched as real WebP
      (WP.com serves JPEG/PNG bytes otherwise)
- [x] Clean all 188 YouTube embeds (in 168 posts) into plain responsive iframes (16:9 via the block-library CSS); Bandcamp
      appears only as links. 5 Jetpack tiled galleries + 1 block gallery flattened to a grid
- [x] Record the 21 category and 360 tag slugs (`_data/wp_taxonomy.yml`), incl. one percent-encoded Japanese tag
- [ ] Final re-sync right before cutover (`.venv/bin/python scripts/wp_export.py all`, then commit)
- [ ] Optional: WordPress.com Tools → Export (WXR + media zip) kept as a backup outside the repo

## 2. Rebuild in Jekyll
- [x] Jekyll 4 site, `permalink: /:year/:month/:day/:title/`, timezone America/Los_Angeles
- [x] Category, tag, author, and year/month/day archives at WordPress URLs, **paginated at `/page/N/` with 10
      per page like WordPress**; home pagination `/page/2/`–`/page/23/`. Spot-checked against live: `/page/2/`,
      `/page/23/`, `/category/reaction-review/page/5/`, `/tag/heavy-metal/page/3/`, `/2023/page/2/` list
      identical posts
- [x] RSS at `/feed/` and `/feed.xml`; `sitemap.xml`; `robots.txt`; `404.html`; favicon/apple-touch icon from the WP site icon
- [x] SEO tags (canonical, OG, Twitter, JSON-LD) on `https://viciousshred.com`. Built for the site root like
      transitsleuth, so the github.io preview isn't a usable duplicate (canonical points at the real domain)
- [x] Port the WordPress.com **Epi** theme: block-library + Epi global styles/stylesheet captured from the live
      site, same block markup in the layouts, Inter self-hosted (OFL), mobile menu toggle in
      `assets/js/navigation.js`
- [x] All Posts / Reaction Vids / Unwrapping Vinyls were paginated query loops (`?query-N-page=`), which static
      hosting can't serve; rebuilt as Liquid lists of every post (same markup). Search hands off to DuckDuckGo
      scoped to the site
- [x] Local link check (`scripts/link_check.py`): all 235 sitemap URLs, 241 sitemap images, every category/tag
      archive and its pages, home pagination, feeds — 911 paths, 0 missing; 0 broken internal links
- [x] Visual check against the live site (headless Chrome, 1440px and 390px): home, post, and mobile match
- [x] README: writing posts, local preview, re-sync

## 3. GitHub
- [x] `git init` locally; GitHub repo `Adron/viciousshred.com` (public, like the other sites)
- [x] `.github/workflows/pages.yml` builds Jekyll 4 and deploys to Pages (enable Pages with Source: GitHub Actions after the first push)
- [ ] First workflow run green; preview at https://adron.github.io/viciousshred.com/

## 4. Domain, DNS, email (Route 53 + CloudFront + SES; runbook in `infra/README.md`)
- [x] Route 53 hosted zone `Z05638863MNC7XJ7O7WNA` mirroring WordPress.com records exactly (A, www, MX); answers verified identical
- [x] ACM certificate (us-east-1) requested for viciousshred.com + www; validation CNAMEs in Route 53 (pending until DNS moves or they're added at WordPress)
- [x] CloudFront function `viciousshred-viewer-request` (tested) + distribution `E3QX6L9KA2GL72` (`d3o632003jcb3t.cloudfront.net`) in front of GitHub Pages
- [ ] **INPUT NEEDED:** list of WordPress email forwards (WordPress.com → Upgrades → Emails → viciousshred.com)
- [x] SES identity + DKIM, S3 bucket, IAM role, Lambda `viciousshred-mail-forward` (empty `FORWARD_MAP`)
- [ ] SES receipt rule `viciousshred-forwarding` + `FORWARD_MAP` (needs the alias list)
- [x] Route 53: SPF, DMARC, DKIM CNAMEs
- [ ] Route 53: MX → SES inbound (right before Phase 1)
- [ ] **INPUT NEEDED:** add the 3 DKIM + 2 ACM CNAMEs (table in `infra/README.md`) in WordPress.com DNS so both verify before the switch
- [ ] **INPUT NEEDED — Phase 1:** WordPress.com nameservers → the 4 Route 53 servers
- [ ] Registry delegates to Route 53; WordPress site still loads; mail test forwards
- [ ] **Phase 2:** attach domain + cert to CloudFront, apex/www A+AAAA alias → CloudFront
- [ ] `http://` and `www.` 301 to `https://viciousshred.com/`

## 5. Registrar transfer to Route 53 + WordPress wind-down (manual at WordPress.com)
- [ ] **INPUT NEEDED:** WordPress.com → Domains → viciousshred.com → Transfer → unlock + get the EPP code
- [ ] Transfer registration to Route 53 Domains (keep Route 53 nameservers; privacy, auto-renew, lock on)
- [ ] **INPUT NEEDED:** turn off WordPress.com plan auto-renew; delete the email forwarders
- [ ] Optional: export the 8 email subscribers
- [ ] After the transfer completes and the site has run clean for a while: close the WordPress.com site/account

## 6. Post-cutover checks
- [ ] Live crawl: every old post, page, category, tag, feed, and sitemap URL returns 200
- [ ] Google Search Console domain property (TXT in Route 53), sitemap submitted
- [ ] Watch for 404s; add redirects as needed

## Known gaps (accepted, same as the other sites)
- Comments, likes, sharing buttons, Jetpack subscriptions don't carry over.
- `?p=123` and `wp.me` shortlinks can't be redirected on static hosting.
- The `/search-for/` page (WordPress search) has no server-side equivalent; it hands off to DuckDuckGo.
- `?query-N-page=` pagination on All Posts / Reaction Vids (query strings are ignored; the page now lists everything).
- WordPress feeds per archive (`/category/x/feed/`, `/comments/feed/`) and image resize URLs (`?w=1024` is ignored; the original loads).
- The footer's placeholder Tumblr / Instagram / Email links (`href="#"`) were replaced with RSS and YouTube.
