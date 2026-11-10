"""Forward mail for @viciousshred.com aliases to a real inbox.

SES receipt rule (us-east-1) -> stores the raw message in S3 -> invokes this function.
The message is re-sent through SES from FORWARD_FROM (a verified viciousshred.com address,
DKIM-signed by SES) with Reply-To set to the original sender, since SES can't send "as" an
outside address.

Environment:
  INBOUND_BUCKET  S3 bucket the receipt rule writes to
  INBOUND_PREFIX  key prefix used by the receipt rule (e.g. "inbound/")
  FORWARD_FROM    envelope/header From for forwarded mail
  FORWARD_MAP     JSON {"alias@viciousshred.com": "destination@example.com", ...}
"""
import email
import json
import logging
import os
from email.header import decode_header, make_header
from email.utils import formataddr, parseaddr

import boto3

log = logging.getLogger()
log.setLevel(logging.INFO)

s3 = boto3.client("s3")
ses = boto3.client("sesv2")

BUCKET = os.environ["INBOUND_BUCKET"]
PREFIX = os.environ.get("INBOUND_PREFIX", "")
FORWARD_FROM = os.environ["FORWARD_FROM"]
ROUTES = {k.lower(): v for k, v in json.loads(os.environ["FORWARD_MAP"]).items()}

# Headers that would make SES reject the message or break authentication once re-sent.
DROP_HEADERS = ("DKIM-Signature", "DomainKey-Signature", "Return-Path", "Sender", "Message-ID")


def decoded(value):
    try:
        return str(make_header(decode_header(value or "")))
    except Exception:
        return value or ""


def rewrite(raw, recipients):
    msg = email.message_from_bytes(raw)
    name, addr = parseaddr(decoded(msg.get("From", "")))

    if "Reply-To" not in msg and addr:
        msg["Reply-To"] = formataddr((name, addr), charset="utf-8")
    del msg["From"]
    msg["From"] = formataddr((f"{name or addr} via Vicious Shred", FORWARD_FROM), charset="utf-8")
    for header in DROP_HEADERS:
        del msg[header]
    msg["X-Original-To"] = ", ".join(recipients)
    return msg.as_bytes()


def handler(event, context):
    for record in event.get("Records", []):
        mail = record["ses"]["mail"]
        receipt = record["ses"]["receipt"]
        message_id = mail["messageId"]

        if receipt.get("spamVerdict", {}).get("status") == "FAIL" or receipt.get("virusVerdict", {}).get("status") == "FAIL":
            log.info("dropping %s: spam=%s virus=%s", message_id,
                     receipt.get("spamVerdict", {}).get("status"), receipt.get("virusVerdict", {}).get("status"))
            continue

        recipients = [r for r in receipt.get("recipients", []) if r.lower() in ROUTES]
        destinations = sorted({ROUTES[r.lower()] for r in recipients})
        if not destinations:
            log.info("no route for %s (recipients=%s)", message_id, receipt.get("recipients"))
            continue

        raw = s3.get_object(Bucket=BUCKET, Key=PREFIX + message_id)["Body"].read()
        ses.send_email(
            FromEmailAddress=FORWARD_FROM,
            Destination={"ToAddresses": destinations},
            Content={"Raw": {"Data": rewrite(raw, recipients)}},
        )
        log.info("forwarded %s for %s to %s", message_id, recipients, destinations)
