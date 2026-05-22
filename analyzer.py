# Log Analyzer
#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


@dataclass
class LogEntry:
    """One successfully parsed log line."""
    timestamp: Optional[datetime]
    ip: Optional[str]
    method: Optional[str]
    path: Optional[str]
    status: Optional[int]
    response_time_ms: Optional[float]
    source: str  # "text" or "json"



IP_RE = re.compile(r"(?:\d{1,3}\.){3}\d{1,3}")

HTTP_METHODS = {
    "GET", "POST", "PUT", "DELETE", "PATCH",
    "HEAD", "OPTIONS", "TRACE", "CONNECT",
}

# Timestamp formats that are commonly used 
TIMESTAMP_FORMATS = (
    "%Y-%m-%dT%H:%M:%SZ",   # 2024-03-15T14:23:01Z
    "%Y-%m-%dT%H:%M:%S",    # 2024-03-15T14:23:01
    "%Y/%m/%d %H:%M:%S",    # 2024/03/15 14:23:01
    "%d-%b-%Y %H:%M:%S",    # 15-Mar-2024 14:23:01
)

#converted into milliseconds, or None when missing/unknown.
def parse_response_time(value) -> Optional[float]:
    
    if value is None:
        return None
    text = str(value).strip().lower()
    if not text or text == "-":
        return None
    try:
        # Check "ms" before "s", because "ms" also ends with "s".
        if text.endswith("ms"):
            return float(text[:-2])
        if text.endswith("s"):
            return float(text[:-1]) * 1000.0
        return float(text)
    except ValueError:
        return None


def parse_timestamp(value) -> Optional[datetime]:
    """Parse a timestamp in any supported format, else return None."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        try:
            return datetime.fromtimestamp(int(text), tz=timezone.utc)
        except (ValueError, OSError, OverflowError):
            return None
    for fmt in TIMESTAMP_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None

# Return a 3-digit status code, or None when missing/unknown

def parse_status(value) -> Optional[int]:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text == "-":
        return None
    if text.isdigit() and len(text) == 3:
        return int(text)
    return None


#    Parse a single JSON-formatted log line.
# Returns a LogEntry, or None when the line is not valid JSON or is missing the core method/path fields.
    
def parse_json_line(line: str) -> Optional[LogEntry]:
    try:
        obj = json.loads(line)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(obj, dict):
        return None

    method = obj.get("method")
    path = obj.get("path")
    if not method or not path:
        return None

    return LogEntry(
        timestamp=parse_timestamp(obj.get("timestamp")),
        ip=obj.get("ip"),
        method=str(method).upper(),
        path=str(path),
        status=parse_status(obj.get("status")),
        response_time_ms=parse_response_time(obj.get("response_time")),
        source="json",
    )


def parse_text_line(line: str) -> Optional[LogEntry]:
    
    tokens = line.split()
    if not tokens:
        return None

    # Locate the IP address.
    ip_index = None
    for i, token in enumerate(tokens):
        if IP_RE.fullmatch(token):
            ip_index = i
            break
    if ip_index is None:
        return None

    ip = tokens[ip_index]
    timestamp = parse_timestamp(" ".join(tokens[:ip_index])) if ip_index else None

    rest = tokens[ip_index + 1:]
    # A line needs at least a method and a path to count as parsed.
    if len(rest) < 2:
        return None

    method = rest[0].upper()
    if method not in HTTP_METHODS:
        return None
    path = rest[1]

    # Status and response time are positional but optional.
    status = parse_status(rest[2]) if len(rest) >= 3 else None
    response_time = parse_response_time(rest[3]) if len(rest) >= 4 else None

    return LogEntry(timestamp, ip, method, path, status, response_time, "text")


def parse_line(line: str) -> Optional[LogEntry]:
   
    stripped = line.strip()
    if not stripped:
        return None
    if stripped.startswith("{"):
        return parse_json_line(stripped)
    return parse_text_line(stripped)



class Stats:

    def __init__(self):
        self.total_lines = 0
        self.parsed_lines = 0
        self.malformed_lines = 0
        self.blank_lines = 0
        self.json_lines = 0
        self.missing_status = 0
        self.missing_response_time = 0

        self.status_counts = Counter()
        self.method_counts = Counter()
        self.endpoint_counts = Counter()
        self.errors_4xx = Counter()
        self.errors_5xx = Counter()

        # Per-endpoint response time totals, used for averages.
        self.endpoint_time_sum = defaultdict(float)
        self.endpoint_time_n = defaultdict(int)

        # (response_time_ms, path, status, line_no) for every timed request.
        self.timed_requests = []

    def add(self, entry: LogEntry, line_no: int) -> None:
        self.parsed_lines += 1
        if entry.source == "json":
            self.json_lines += 1

        self.method_counts[entry.method] += 1
        self.endpoint_counts[entry.path] += 1

        if entry.status is None:
            self.missing_status += 1
        else:
            self.status_counts[entry.status] += 1
            if 400 <= entry.status < 500:
                self.errors_4xx[entry.path] += 1
            elif 500 <= entry.status < 600:
                self.errors_5xx[entry.path] += 1

        if entry.response_time_ms is None:
            self.missing_response_time += 1
        else:
            rt = entry.response_time_ms
            self.endpoint_time_sum[entry.path] += rt
            self.endpoint_time_n[entry.path] += 1
            self.timed_requests.append((rt, entry.path, entry.status, line_no))


def analyze_file(path: str) -> Stats:
    
    stats = Stats()
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        for line_no, raw in enumerate(handle, start=1):
            stats.total_lines += 1
            if not raw.strip():
                stats.blank_lines += 1
                continue
            entry = parse_line(raw)
            if entry is None:
                stats.malformed_lines += 1
                continue
            stats.add(entry, line_no)
    return stats



def percentile(sorted_values, pct: float) -> Optional[float]:
    """Linear-interpolation percentile of an already-sorted list."""
    if not sorted_values:
        return None
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = (len(sorted_values) - 1) * (pct / 100.0)
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return sorted_values[int(rank)]
    return (sorted_values[low]
            + (sorted_values[high] - sorted_values[low]) * (rank - low))


def _format_ms(value: Optional[float]) -> str:
    return f"{value:.1f} ms" if value is not None else "n/a"


def print_report(stats: Stats, path: str = "", top_n: int = 5) -> None:
    """Print the on-call style report to stdout."""
    rule = "=" * 60
    response_times = sorted(rt for rt, _, _, _ in stats.timed_requests)

    print(rule)
    print("  LOG ANALYZER REPORT")
    if path:
        print(f"  File: {path}")
    print(rule)

    # Parsing summary 
    print("\nPARSING SUMMARY")
    print(f"  Total lines             {stats.total_lines:>8}")
    print(f"  Parsed lines            {stats.parsed_lines:>8}")
    print(f"  Malformed lines         {stats.malformed_lines:>8}")
    print(f"  Blank lines             {stats.blank_lines:>8}")
    print(f"  JSON lines parsed       {stats.json_lines:>8}")
    print(f"  Missing status          {stats.missing_status:>8}")
    print(f"  Missing response time   {stats.missing_response_time:>8}")

    # Status codes 
    print("\nSTATUS CODE COUNTS")
    if stats.status_counts:
        for code, count in sorted(stats.status_counts.items()):
            print(f"  {code:<6} {count:>8}")
    else:
        print("  (none)")

    # HTTP methods 
    print("\nHTTP METHOD COUNTS")
    if stats.method_counts:
        for method, count in stats.method_counts.most_common():
            print(f"  {method:<8} {count:>8}")
    else:
        print("  (none)")

    # Top endpoints by request count 
    print(f"\nTOP {top_n} ENDPOINTS BY REQUEST COUNT")
    if stats.endpoint_counts:
        for endpoint, count in stats.endpoint_counts.most_common(top_n):
            print(f"  {count:>6}  {endpoint}")
    else:
        print("  (none)")

    # Top endpoints by average response time -----------------------------
    print(f"\nTOP {top_n} ENDPOINTS BY AVG RESPONSE TIME")
    averages = [
        (stats.endpoint_time_sum[p] / stats.endpoint_time_n[p],
         p, stats.endpoint_time_n[p])
        for p in stats.endpoint_time_n
    ]
    if averages:
        averages.sort(key=lambda row: row[0], reverse=True)
        for avg, endpoint, n in averages[:top_n]:
            print(f"  {avg:>9.1f} ms  {endpoint}  ({n} requests)")
    else:
        print("  (none)")

    # Error endpoints -----------------------------------------------------
    print(f"\nTOP {top_n} 4xx ERROR ENDPOINTS")
    if stats.errors_4xx:
        for endpoint, count in stats.errors_4xx.most_common(top_n):
            print(f"  {count:>6}  {endpoint}")
    else:
        print("  (none)")

    print(f"\nTOP {top_n} 5xx ERROR ENDPOINTS")
    if stats.errors_5xx:
        for endpoint, count in stats.errors_5xx.most_common(top_n):
            print(f"  {count:>6}  {endpoint}")
    else:
        print("  (none)")

    # Response time summary ----------------------------------------------
    print("\nRESPONSE TIME")
    if response_times:
        avg = sum(response_times) / len(response_times)
        print(f"  Average   {_format_ms(avg)}")
        print(f"  P50       {_format_ms(percentile(response_times, 50))}")
        print(f"  P95       {_format_ms(percentile(response_times, 95))}")
        print(f"  P99       {_format_ms(percentile(response_times, 99))}")
    else:
        print("  (no timed requests)")

    # Slowest individual requests ----------------------------------------
    print(f"\nSLOWEST {top_n} INDIVIDUAL REQUESTS")
    if stats.timed_requests:
        slowest = sorted(stats.timed_requests,
                         key=lambda row: row[0], reverse=True)[:top_n]
        for rt, endpoint, status, line_no in slowest:
            status_text = str(status) if status is not None else "-"
            print(f"  {rt:>9.1f} ms  {endpoint:<24} "
                  f"status {status_text:<5} line {line_no}")
    else:
        print("  (no timed requests)")

    print("\n" + rule)




def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Analyze a server log file and print a summary report."
    )
    parser.add_argument("logfile", help="path to the log file to analyze")
    parser.add_argument(
        "--top", type=int, default=5,
        help="how many rows to show in each 'top' section (default: 5)",
    )
    args = parser.parse_args(argv)

    try:
        stats = analyze_file(args.logfile)
    except FileNotFoundError:
        print(f"error: file not found: {args.logfile}", file=sys.stderr)
        return 1
    except IsADirectoryError:
        print(f"error: not a file: {args.logfile}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"error: could not read {args.logfile}: {exc}", file=sys.stderr)
        return 1

    print_report(stats, args.logfile, top_n=max(1, args.top))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
