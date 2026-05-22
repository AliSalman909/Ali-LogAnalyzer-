"""
Basic tests for the log parser.

Run from the project root:
    pytest
"""

import os
import sys

# Make the project root importable so `import analyzer` works no matter
# which directory pytest is started from.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import analyzer


def test_normal_text_line_parses():
    """A standard text log line is parsed into the expected fields."""
    entry = analyzer.parse_line(
        "2024-03-15T14:23:01Z 192.168.1.42 GET /api/users 200 142ms"
    )
    assert entry is not None
    assert entry.method == "GET"
    assert entry.path == "/api/users"
    assert entry.status == 200
    assert entry.response_time_ms == 142.0
    assert entry.source == "text"


def test_json_line_parses():
    """A JSON-formatted log line is parsed into the expected fields."""
    line = (
        '{"timestamp":"2024-03-15T14:23:01Z","ip":"192.168.1.42",'
        '"method":"GET","path":"/api/users","status":200,'
        '"response_time":"142ms"}'
    )
    entry = analyzer.parse_line(line)
    assert entry is not None
    assert entry.source == "json"
    assert entry.method == "GET"
    assert entry.status == 200
    assert entry.response_time_ms == 142.0


def test_seconds_convert_to_milliseconds():
    """0.142s must be normalised to 142ms; ms and bare numbers pass through."""
    assert analyzer.parse_response_time("0.142s") == 142.0
    assert analyzer.parse_response_time("142ms") == 142.0
    assert analyzer.parse_response_time("142") == 142.0


def test_missing_status_does_not_crash():
    """A '-' status code is treated as missing without raising."""
    entry = analyzer.parse_line(
        "2024-03-15T14:23:01Z 192.168.1.42 GET /api/users - 142ms"
    )
    assert entry is not None
    assert entry.status is None
    assert entry.response_time_ms == 142.0


def test_malformed_line_returns_none():
    """Junk, broken JSON, and blank lines all return None instead of raising."""
    assert analyzer.parse_line("this is not a log line") is None
    assert analyzer.parse_line("{ broken json") is None
    assert analyzer.parse_line("") is None
