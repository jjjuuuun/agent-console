# agent-console-safe-regex

A small library that **validates, compiles, and runs with a time limit** regular expressions that users put into settings data (routing rules, manual selection syntax, console entry syntax, and so on).
It has no internal dependencies (external dependency: `regex`).

There are three layers of defense.

1. **Run time limit (main defense)**: `timeout` per match (default 0.1 seconds). Exceeding it raises `RegexTimeoutError`.
   `regex` measures this time with C `clock()` (on Linux, the CPU time of the whole process), so when other threads in the same process
   are busy, even a short match can time out. So the GIL is held during a match
   (`concurrent=False`), and when a timeout happens but the CPU this thread used in that attempt (`time.thread_time`) is
   less than half of `timeout`, it is blamed on other threads' CPU and retried (at most 3 attempts including the first, then it times out).
   A runaway match uses its own CPU, so it still ends on the first attempt.
2. **Input length limit**: only the first `max_input_chars` of the input (default 4096 characters) are checked.
3. **Validation heuristics (secondary)**: pattern length (default 512 characters), syntax errors, required named groups, and
   rejection of repetition inside a repeated group (`(a+)+`, `(.*a){20}`, `(x+){2,}`) and of overlapping
   alternatives inside a repeated group (`(a|a)*`, `(a|ab)+`, `(.|x)*`). Atomic groups `(?>...)` and possessive quantifiers (`a++`) are
   allowed. The heuristics are not complete, so the time limit is the final guarantee.

## Dependencies: what / why / alternatives

- **What**: [`regex`](https://pypi.org/project/regex/) (Apache-2.0, actively maintained). It offers syntax compatible with `re`
  plus a per-match `timeout=` argument.
- **Why**: the standard `re` has no time limit, so one user regex can stall the server event loop.
  `regex` checks the timeout inside the match engine, so it caps the cost of one match without extra processes or threads.
  Result types are wrapped in `SafeMatch` so the implementation library is not exposed in the public API.
- **Alternatives**
  - Run `re` in a separate process and kill it on timeout: it can be cut off reliably, but IPC and process cost per match
    is high (milliseconds to tens of milliseconds), too much for routing that runs several rules per input. Spawning is slow on Windows.
  - Thread + timeout: Python threads cannot be killed, so a runaway match keeps using CPU.
  - `google-re2` (linear-time engine): no backtracking at all, but it does not support backreferences or lookaround, so it differs from existing
    `re` syntax and adds a native build dependency.

## Installation

```bash
uv sync --all-packages                        # inside the workspace
uv pip install ./packages/py/base/ac-safe-regex    # standalone, from another project
```

## Minimal usage

```python
>>> from agent_console_safe_regex import RegexTimeoutError, UnsafeRegexError, compile_user_regex

>>> pat = compile_user_regex(
...     r"^@(?P<category>[\w-]+)\s+", required_groups=("category",), timeout=0.05
... )
>>> try:
...     m = pat.search("@spec 새 기능")
... except RegexTimeoutError:
...     m = None  # the caller decides (for example, record it as no match)
>>> m.group("category"), m.end, m.span("category")
('spec', 6, (1, 5))

>>> try:  # a settings error to show the user at validation time
...     compile_user_regex("(a+)+")
... except UnsafeRegexError as exc:
...     print(str(exc).split("(")[0])
반복되는 그룹 안에 다시 반복이 있다

>>> [(m.start, m.text) for m in compile_user_regex(r"tok_\d+").finditer("a tok_1 b tok_22")]
[(2, 'tok_1'), (10, 'tok_22')]

```

For validation only, use `check_user_regex(pattern, required_groups=...)`.
When you need every match (for example, masking secrets in a text), use `pat.finditer(text)`. The time limit applies once to the whole
scan, and named group positions come from `SafeMatch.span(name)`.

## Development and standalone reuse

This folder is a standalone project. Copy only this folder and the commands below still work. Internal dependencies
are declared as a name plus a version range, so outside the repository pass the wheelhouse (`uv run poe wheels` in the repository → `dist/wheelhouse`)
as a find-links path (`uv sync --find-links <wheelhouse>`). Check inside the repository: `uv run poe portability --package ac-safe-regex`.

```bash
uv sync                  # includes the dev group (pytest, mypy, ruff, internal packages the tests use)
uv run ruff check . && uv run mypy && uv run pytest
```

## Testing

```bash
uv run pytest packages/py/base/ac-safe-regex/tests
```
