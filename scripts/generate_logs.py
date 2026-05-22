#!/usr/bin/env python3
"""
Generate a representative server log file for testing the analyzer.

Usage:
    python scripts/generate_logs.py --output logs/sample.log --lines 1000
    python scripts/generate_logs.py --output logs/sample.log --lines 5000 --seed 7

The generated file deliberately mixes:
  - normal text log lines
  - several timestamp formats (ISO, slash, named-month, epoch)
  - ms / s / bare-number response times
  - missing status codes ("-")
  - extra fields (quoted user agents / referrers with spaces)
  - JSON-formatted lines
  - completely malformed lines
  - blank lines
"""

import argparse
import json
import os
import random
from datetime import datetime, timedelta

ENDPOINTS = [
    "/api/users", "/api/users/12", "/api/login", "/api/logout",
    "/api/orders", "/api/orders/88", "/api/products", "/api/search",
    "/api/report", "/health", "/static/app.js", "/static/style.css",
]
# GET is weighted heavier so the mix looks like real traffic.
METHODS = ["GET", "GET", "GET", "POST", "POST", "PUT", "DELETE"]
STATUSES = [200, 200, 200, 200, 201, 301, 304, 400, 401, 403, 404, 500, 502, 503]
USER_AGENTS = [
    '"Mozilla/5.0 (Windows NT 10.0; Win64; x64)"',
    '"curl/8.4.0"',
    '"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"',
]
REFERRERS = [
    '"https://example.com/home"',
    '"https://example.com/search?q=test"',
]

MALFORMED = [
    "this is not a log line at all",
    "GET /api/users",                       # no ip / no timestamp
    "2024-03-15T14:23:01Z GET 200",         # missing ip
    "{ broken json",                        # invalid json
    "????",
    "2024-03-15 oops 192.168 GET",          # junk fields
]


def random_ip():
    return (f"{random.randint(10, 200)}.{random.randint(0, 255)}."
            f"{random.randint(0, 255)}.{random.randint(1, 254)}")


def format_timestamp(when):
    """Return the timestamp in one of several formats chosen at random."""
    style = random.choice(["iso", "slash", "named", "epoch"])
    if style == "iso":
        return when.strftime("%Y-%m-%dT%H:%M:%SZ")
    if style == "slash":
        return when.strftime("%Y/%m/%d %H:%M:%S")
    if style == "named":
        return when.strftime("%d-%b-%Y %H:%M:%S")
    return str(int(when.timestamp()))


def format_response_time(ms):
    """Return a response time in ms, s, or bare-number form."""
    style = random.choice(["ms", "s", "plain"])
    if style == "ms":
        return f"{ms}ms"
    if style == "s":
        return f"{ms / 1000:.3f}s"
    return str(ms)


def make_text_line(when):
    ts = format_timestamp(when)
    ip = random_ip()
    method = random.choice(METHODS)
    path = random.choice(ENDPOINTS)
    # ~8% of lines have a missing status code.
    status = "-" if random.random() < 0.08 else random.choice(STATUSES)
    parts = [ts, ip, method, path, str(status)]
    # ~85% of lines include a response time.
    if random.random() < 0.85:
        parts.append(format_response_time(random.randint(5, 1800)))
    # ~30% of lines carry extra fields (referrer + user agent).
    if random.random() < 0.30:
        parts.append(random.choice(REFERRERS))
        parts.append(random.choice(USER_AGENTS))
    return " ".join(parts)


def make_json_line(when):
    obj = {
        "timestamp": when.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ip": random_ip(),
        "method": random.choice(METHODS),
        "path": random.choice(ENDPOINTS),
        "status": random.choice(STATUSES),
        "response_time": format_response_time(random.randint(5, 1800)),
    }
    return json.dumps(obj)


def generate(lines):
    """Yield `lines` log lines as a mix of all supported shapes."""
    when = datetime(2024, 3, 15, 14, 0, 0)
    for _ in range(lines):
        when += timedelta(seconds=random.randint(1, 5))
        roll = random.random()
        if roll < 0.10:
            yield random.choice(MALFORMED)
        elif roll < 0.14:
            yield ""                       # blank line
        elif roll < 0.30:
            yield make_json_line(when)
        else:
            yield make_text_line(when)


def main():
    parser = argparse.ArgumentParser(description="Generate a test log file.")
    parser.add_argument("--output", required=True, help="output file path")
    parser.add_argument("--lines", type=int, default=1000,
                        help="number of lines to generate (default: 1000)")
    parser.add_argument("--seed", type=int, default=None,
                        help="optional random seed for reproducible output")
    args = parser.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    out_dir = os.path.dirname(os.path.abspath(args.output))
    os.makedirs(out_dir, exist_ok=True)

    with open(args.output, "w", encoding="utf-8") as handle:
        for log_line in generate(args.lines):
            handle.write(log_line + "\n")

    print(f"Wrote {args.lines} lines to {args.output}")


if __name__ == "__main__":
    main()
