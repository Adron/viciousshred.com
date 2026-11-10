# viciousshred.com infrastructure (AWS)

```
visitor ──DNS──▶ Route 53 (viciousshred.com zone)
        ──HTTPS─▶ CloudFront E3QX6L9KA2GL72  (ACM cert, viewer-request function)
                    └─▶ GitHub Pages: https://adron.github.io/viciousshred.com/  (built by .github/workflows/pages.yml)

mail ──MX──▶ SES inbound (us-east-1) ──▶ S3 viciousshred-inbound-mail-196936048600/inbound/
                                     └─▶ Lambda viciousshred-mail-forward ──SES──▶ destination inbox
```

Same design as transitsleuth.com; see that repo's `infra/README.md` for why CloudFront sits in front of
GitHub Pages (WordPress sends HSTS, so the certificate must exist before DNS moves).

## Resources (AWS account 196936048600)

| Resource | ID / value |
|----------|------------|
| Route 53 hosted zone | `Z05638863MNC7XJ7O7WNA` |
| Nameservers | `ns-502.awsdns-62.com`, `ns-991.awsdns-59.net`, `ns-1418.awsdns-49.org`, `ns-1850.awsdns-39.co.uk` |
| ACM certificate (us-east-1) | `arn:aws:acm:us-east-1:196936048600:certificate/8091d2c9-0325-4e44-a29a-29e14dd243e8` (viciousshred.com, www) |
| CloudFront distribution | `E3QX6L9KA2GL72` → `d3o632003jcb3t.cloudfront.net` (no aliases until Phase 2) |
| CloudFront function | `viciousshred-viewer-request`; source in [`cloudfront-viewer-request.js`](cloudfront-viewer-request.js) |
| SES identity (us-east-1) | `viciousshred.com` (Easy DKIM; 3 `_domainkey` CNAMEs in Route 53) |
| SES receipt rule | `viciousshred-forwarding` in the shared active rule set `substratal-prod-inbound` (created once the alias list is known) |
| S3 bucket | `viciousshred-inbound-mail-196936048600` (private, `inbound/` expires after 30 days) |
| Lambda | `viciousshred-mail-forward` (python3.13, arm64); source in [`email-forwarder/`](email-forwarder/lambda_function.py) |
| IAM role | `viciousshred-mail-forward` (read `inbound/*`, send as viciousshred.com, own logs) |
| Log group | `/aws/lambda/viciousshred-mail-forward` (90-day retention) |

CloudFront config is cloned from the transitsleuth distribution (CachingOptimized, SecurityHeadersPolicy,
PriceClass_100, HTTP/2+3, IPv6), with origin path `/viciousshred.com`.

## Records

WordPress mirror (live in Route 53 now): apex A `192.0.78.24`, `192.0.78.25`; `www` CNAME → apex;
MX `0 smtp-fwd.wordpress.com` (TTL 300).

Already added for the move: ACM validation CNAMEs, SES DKIM CNAMEs, SPF `v=spf1 include:amazonses.com ~all`,
DMARC `v=DMARC1; p=none;`.

Add these 5 CNAMEs in **WordPress.com DNS** too, so ACM and SES verify before the nameserver switch:

| Name | Value |
|------|-------|
| `_2fe1ce62e33d945f7bf3e9f9f3ed74dd` | `_edef4aa4eef42e27cd74518ad076818b.wzccmgtwzk.acm-validations.aws.` |
| `_b109a3d02a67b0b84d1d909283e1c32f.www` | `_92944edf8d4004df3b73fbd3bbfcb56c.wzccmgtwzk.acm-validations.aws.` |
| `kvp46rabpz4jwngeg7pgie54vuv4bvdk._domainkey` | `kvp46rabpz4jwngeg7pgie54vuv4bvdk.dkim.amazonses.com` |
| `g7ig5xuq7s2ybooygmzi25ly54jxb4jq._domainkey` | `g7ig5xuq7s2ybooygmzi25ly54jxb4jq.dkim.amazonses.com` |
| `rlrkgwqbry6kaorkyyeqcuydk5mneqvh._domainkey` | `rlrkgwqbry6kaorkyyeqcuydk5mneqvh.dkim.amazonses.com` |

## Cutover runbook

1. **Before Phase 1:** alias list in the Lambda's `FORWARD_MAP` and the receipt rule; SES DKIM `SUCCESS`; ACM
   `ISSUED`; Route 53 MX → `10 inbound-smtp.us-east-1.amazonaws.com`.
2. **Phase 1:** WordPress.com → Domains → viciousshred.com → Name servers → custom → the 4 Route 53 servers.
   The site keeps serving from WordPress (A records unchanged); mail now flows through SES.
3. **Phase 2:** attach aliases + ACM cert to `E3QX6L9KA2GL72`, verify with `curl --resolve`, then alias apex and
   `www` A+AAAA to CloudFront. Rollback: put the A records back to `192.0.78.24/25`.
4. **Phase 3:** registrar transfer to Route 53 Domains with the EPP code from WordPress.com; then wind down
   WordPress.

## Email forwarding

- Forwarded mail arrives From "Sender via Vicious Shred" <forwarder@viciousshred.com>, Reply-To the original sender.
- **Add or change an alias:** add it to the receipt rule's recipients *and* to the Lambda's `FORWARD_MAP` (JSON).
- **Deploy Lambda code changes:** zip `email-forwarder/lambda_function.py` and
  `aws lambda update-function-code --function-name viciousshred-mail-forward --zip-file fileb://fwd.zip`.
