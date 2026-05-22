# Answers

## 1. How to run

The project runs on a fresh machine with **Python 3.8 or newer** and nothing
else. Only the test suite needs an extra package.

**Install (only required if you want to run the tests):**

```
pip install pytest
```

**Step 1 — generate a representative log file:**

```
python scripts/generate_logs.py --output logs/sample.log --lines 1000
```

The `logs/` folder does not need to exist beforehand; the script creates it.
An optional `--seed` makes the output reproducible (e.g. `--seed 7`).

**Step 2 — run the analyzer on that file (or any log file):**

```
python analyzer.py logs/sample.log
```

The analyzer accepts any path as its argument and prints the report to the
terminal. It does not assume a filename, a number of lines, or fixed values.
Use `--top 10` to show more rows in each ranked section. To save the report,
redirect it: `python analyzer.py logs/sample.log > report.txt`.

**Step 3 — run the tests:**

```
pytest
```

Run from the project root. The test file adds the project root to `sys.path`,
so `pytest` works regardless of the directory it is started from.

## 2. Stack choice

I built this as a **Python 3 command-line tool using only the standard
library** (`argparse`, `json`, `re`, `datetime`, `collections`). The test
suite uses `pytest`.

A log analyzer is fundamentally a string-parsing and counting problem, and
Python's standard library covers all of it. Choosing standard-library-only
means there is nothing to install to run the core tool — a grader can clone
the repo and run it immediately, which directly serves the "single command
on a fresh machine" requirement. A CLI that prints a report is also the
fastest thing for an on-call engineer to run and read.

**Why i didnt go for other choices**

- Perfromance would be fine if i went with a web dashboard or a compile language one but due to time cosntraints, this approach seemed the msot sensible. I have my final exams fir university ongoing currently and that provided me with less time for this. 

## 3. One real edge case

**Response-time unit conversion** — `analyzer.py`, function
`parse_response_time` (lines 73–96).

Response times appear in three forms the spec lists: `142ms`, `0.142s`, and a
bare `142`. They must all be normalised to milliseconds, otherwise averages
and percentiles mix incompatible units and become meaningless.

The non-obvious trap is suffix matching: the string `"ms"` **also ends with
`"s"`**. The code checks `endswith("ms")` *first* (line 91) and only then
falls through to `endswith("s")` (line 93), where line 94 multiplies by 1000
to convert seconds to milliseconds. A bare number is treated as milliseconds,
and anything unparseable returns `None`.

**What happens without this handling:** if the `"s"` check ran before the
`"ms"` check, a value like `142ms` would match the `"s"` branch, get its last
character stripped to `142m`, fail to convert to a number, and be discarded.
Every millisecond-formatted response time in the file would be silently
dropped and counted as "missing response time" — quietly corrupting the
average, P50, P95, P99, and the slowest-request ranking, with no error to
signal that anything went wrong. This case is covered directly by
`test_seconds_convert_to_milliseconds` in `tests/test_parser.py`.

## 4. AI usage

I used AI in three places, and reviewed and tested everything it produced
myself:

- **Claude (chat).** I asked it to help scaffold the project structure and
  the required files, to brainstorm the full set of edge cases the spec
  implied (alternate timestamp formats, response-time unit conversions,
  missing status codes, appended quoted fields, malformed lines, JSON lines),
  and to draft initial versions of the parser functions.
- **Claude (chat).** I asked it to help word this `ANSWERS.md` and the
  `README.md` clearly.
- **Claude Code.** I asked it to add a high-malformed-rate warning to the
  report and a matching test, so the tool surfaces format mismatches instead
  of printing an empty-looking report.

**Something I changed and why:** the AI's first parser draft split each line
on whitespace and read fields by fixed index. That breaks on two cases the
spec explicitly requires — timestamps that themselves contain a space
(`2024/03/15 14:23:01`) and quoted user-agent or referrer fields that contain
spaces. I changed the approach to **anchor on the IP address**: the parser
finds the IPv4 token, treats everything before it as the timestamp, and reads
the fields after it positionally, ignoring any extra fields. This is what
`parse_text_line` does now. I also cut report sections the draft included
that did not add value for someone on call.

## 5. Honest gap

The clearest gap is **format scope**. The tool reliably handles the format
the brief describes — space-delimited web access lines plus the JSON variant
"bolted on" — but it treats any genuinely different log format as malformed.
While testing, I ran it against two real-world logs in other formats (an
OpenStack `nova` service log and an Apache error log). It did not crash and
it did not invent data: it counted those lines as malformed and, with the
high-malformed-rate warning, flagged that the file likely does not match the
expected format. But it could not actually analyze them.

**With another day** I would add a small pluggable format-detection layer: a
registry of parser strategies, each with a cheap "can this parser handle this
line?" check, so the tool could recognise and parse a few more common log
shapes instead of only flagging them as unparseable. A smaller secondary gap:
percentile calculation keeps every response time in memory, so memory grows
with the number of timed lines; a production version would use a streaming
percentile estimate (e.g. a t-digest) and a bounded heap for slowest
requests.

---

## Scope and limitations (structured, semi-structured, unstructured)

Server logs fall into three broad categories, and this tool deliberately
targets the first two:

- **Semi-structured logs — primary target.** The standard line in this
  assessment (`2024-03-15T14:23:01Z 192.168.1.42 GET /api/users 200 142ms`)
  is semi-structured: a consistent field order and pattern, but with messy
  real-world variation and no rigid delimiter, so it needs a custom parser.
  `parse_text_line` handles this using the IP-address anchor described above.

- **Structured logs — supported.** JSON-formatted lines have an explicit,
  consistent schema. `parse_json_line` handles these natively. This covers
  the "slightly different format someone bolted on" case from the brief.

- **Unstructured logs — not parsed, but handled safely.** Free-form text
  logs (application logs, stack traces, Apache error-log messages) have no
  consistent field layout. The tool does not extract data from them; it
  counts them as malformed and, if they dominate the file, the
  high-malformed-rate warning makes the mismatch obvious instead of printing
  an empty report.

**Datasets this tool will not analyze** (and where it will instead show the
warning rather than crash or silently drop data): logs in unrelated formats
such as OpenStack `nova` service logs, Apache error logs, syslog, and CSV
exports. This is a conscious scope decision — the brief defines a specific
log shape and states that test files follow it, with only 5–10% deviation in
the listed ways. The tool is built to be correct and graceful on that shape
and its documented deviations, and to clearly signal anything outside it.
