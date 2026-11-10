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
- [ ] Export all 228 posts (2011-09-18 → 2023-10-16) and 6 pages (`/about/`, `/all-posts/`,
      `/reaction-vids/`, `/reviews/`, `/reactions/`, `/search-for/`) from the WordPress.com API
- [ ] Keep exact WordPress permalinks (`/YYYY/MM/DD/slug/`)
- [ ] Download all uploads to `/wp-content/uploads/` at the original paths; strip GPS EXIF
- [ ] Convert YouTube (≈400 refs) and Bandcamp embeds to responsive iframes
- [ ] Record the 21 category and 360 tag slugs so archive URLs match WordPress
- [ ] Final re-sync right before cutover
- [ ] Optional: WordPress.com Tools → Export (WXR + media zip) kept as a backup outside the repo

## 2. Rebuild in Jekyll
- [ ] Jekyll 4 site, `permalink: /:year/:month/:day/:title/`, timezone America/Los_Angeles
- [ ] Category, tag, and date archives at WordPress URLs; home pagination at `/page/N/`
- [ ] RSS at `/feed/` and `/feed.xml`; `sitemap.xml`; `robots.txt`; `404.html`
- [ ] SEO tags (canonical, OG, Twitter) on `https://viciousshred.com`; github.io preview `noindex`
- [ ] Port the WordPress.com **Epi** theme
- [ ] Local link check: every URL in the live WordPress sitemap resolves in the build
- [ ] Visual check against the live site, desktop and mobile
- [ ] README: writing posts, local preview, re-sync

## 3. GitHub
- [x] `git init` locally; GitHub repo `Adron/viciousshred.com` (public, like the other sites)
- [ ] `.github/workflows/pages.yml` builds Jekyll 4 and deploys to Pages (Source: GitHub Actions)
- [ ] First workflow run green; preview at https://adron.github.io/viciousshred.com/

## 4. Domain, DNS, email (Route 53 + CloudFront + SES; runbook in `infra/README.md`)
- [ ] Route 53 hosted zone mirroring WordPress.com records exactly (A, www, MX)
- [ ] ACM certificate (us-east-1) for viciousshred.com + www, DNS-validated in Route 53
- [ ] CloudFront function (www→apex 301, `/feed/`→XML, directory index) + distribution in front of GitHub Pages
- [ ] **INPUT NEEDED:** list of WordPress email forwards (WordPress.com → Upgrades → Emails → viciousshred.com)
- [ ] SES inbound forwarding: identity + DKIM, S3 bucket, Lambda `viciousshred-mail-forward`, receipt rule
- [ ] Route 53: MX → SES inbound, SPF, DMARC, DKIM CNAMEs
- [ ] **INPUT NEEDED:** add the 3 DKIM CNAMEs in WordPress.com DNS (so SES verifies before the switch)
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
- The `/search-for/` page (WordPress search) has no server-side equivalent.
