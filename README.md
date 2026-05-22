# Log Analyzer

A command-line tool that reads a server log file and prints an on-call style summary report: parsing counts, status/method breakdowns, top endpoints, error endpoints, response-time percentiles, and the slowest individual requests.

The analyzer streams the file line by line, handles multiple timestamp and response-time formats, parses JSON-formatted lines, and warns you if the file looks like it wasn't understood (>= 40% malformed lines).

## Requirements

- Python 3.8+
- Standard library only (no `pip install` needed to run the analyzer)
- `pytest` for the test suite only:

```
pip install pytest
```

## Project layout

```
Ali-LogAnalyzer/
├── analyzer.py            # CLI tool — parser, aggregator, report printer
├── README.md
├── ANSWERS.md             # design decisions and trade-offs
├── .gitignore
├── scripts/
│   └── generate_logs.py   # generates a representative test log file
└── tests/
    └── test_parser.py     # pytest tests for the parser
```

> `logs/` is created locally when you run the generator but is excluded from the repo via `.gitignore`.

## Usage

### 1. Generate a test log

```
python scripts/generate_logs.py --output logs/sample.log --lines 1000
```

Use `--seed` for reproducible output:

```
python scripts/generate_logs.py --output logs/sample.log --lines 1000 --seed 7
```

The generated file mixes normal text lines, multiple timestamp formats (`ISO`, `slash`, `named-month`, `epoch`), response times in `ms`/`s`/bare-number form, missing status codes, extra fields (referrers, user agents), JSON lines, malformed lines, and blank lines.

### 2. Run the analyzer

```
python analyzer.py logs/sample.log
```

Show more rows in each "top" section:

```
python analyzer.py logs/sample.log --top 10
```

Test the malformed-file warning with a garbage file:

```
python analyzer.py logs/garbage.log
```

### 3. Run the tests

```
pytest
```

Run a single test by name:

```
pytest tests/test_parser.py::test_seconds_convert_to_milliseconds
```

## Report sections

| Section | What it shows |
|---|---|
| Parsing summary | Total / parsed / malformed / blank / JSON line counts, missing fields |
| Status code counts | Count per HTTP status code |
| HTTP method counts | Count per method (GET, POST, …) |
| Top endpoints by request count | Most-hit paths |
| Top endpoints by avg response time | Slowest paths on average |
| Top 4xx / 5xx error endpoints | Paths with the most client/server errors |
| Response time | Average, P50, P95, P99 across all timed requests |
| Slowest individual requests | Slowest N requests with path, status, and line number |

If >= 40% of non-blank lines could not be parsed, a warning block is printed before the report so you know the results may be incomplete.
