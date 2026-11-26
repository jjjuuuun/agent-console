# agent-console-example-wiki-search

An example and writing guide that adds a wiki search method (index) with **a single plugin package**.
No engine, server, or web code changes. Once installed and chosen in the settings, wiki search runs on this index; when it is not chosen or is
removed, search goes back to the mod-wiki default method (the administrator `search.backend`, or `search.fallback` when it is missing).

Search method `example-inverted`
- Splits bodies into terms and keeps an inverted index `term -> set of paths` **in memory**. There is no external service or file, and it disappears when the process
  ends (the server fills it again from the pages at startup; the index is a cache that can be rebuilt).
- A query term matches the indexed terms that contain it (partial match: `위키` inside `위키는`). Every term must appear
  somewhere in the path, title, tags, aliases, or body. Scores, snippets, and highlight ranges (`marks`) are the same as the contract.
- The term splitting rule is option data (defaults in `data/defaults.json`): `tokenizer` picks a regular expression from a name table (`tokenizers`),
  or `token_pattern` gives one directly. The default (`whitespace`) gives the same results as substring search. Other rules, such as `word`,
  can miss queries that cross term boundaries (`a-b`).
- Dependencies: the contract (`agent-console-contracts`), the wiki library (`agent-console-wiki`, the index protocol and `search_marks`), and
  `agent-console-secret-rules` (masks secrets before they go into the index). It does not import the server module (`mod-wiki`); only the tests use it.

This package is not a uv workspace member. When it is not installed, it changes nothing.

## How to build an index

An index follows the `agent_console_wiki.WikiSearchIndex` protocol (`id`, `degraded`, `hashes`, `update`, `remove`, `rebuild`, `search`,
`close`). What you register is a **factory** `(root, options) -> index`. `root` = the index file location (ignored when the index writes no files), and
`options` = the values from the administrator and user settings (`tokenizer`, `case_insensitive`, `max_results`, and the values this example reads).

Using only this example's index, without a server:

```python
>>> from agent_console_example_wiki_search import make_index
>>> from agent_console_wiki import WikiSearchDocument
>>> index = make_index({"case_insensitive": True})
>>> index.update([WikiSearchDocument(path="guide/intro", title="소개", text="이 위키는 팀의 약속을 적는다.",
...                                  content_hash="h1")])
1
>>> index.update([WikiSearchDocument(path="guide/intro", title="소개", text="이 위키는 팀의 약속을 적는다.",
...                                  content_hash="h1")])
0
>>> hit = index.search("위키").items[0]
>>> (hit.path, hit.snippet, [(m.start, m.end) for m in hit.marks])
('guide/intro', '이 위키는 팀의 약속을 적는다.', [(2, 4)])
>>> index.search("없는낱말").items
[]

```

<!-- doctest: keep a blank line after expected output so the closing fence is not read as output. -->

Rules
1. **Options are data**: values that can change, such as the term splitting rule, are not in code; they come as options (package data defaults +
   settings overrides). Unknown option values (such as `tokenizer: trigram` passed by mod-wiki) fall back to the default.
2. **The contract tests define the semantics**: every term must match; the score is title 8, path 4, tags/aliases 4, 1 per page, with ties
   in path order. The body does not count toward the score (so that every index gives the same order).
3. **Mask secrets before they go into the index**: the index must not contain the original text (neither snippets nor search).
4. **`update` skips documents with the same hash**: the incremental update key is `content_hash`.
5. **Thread safety, `close` may be called more than once, and mod-wiki catches factory exceptions** (it works without an index).

## Registration

One entry point in `pyproject.toml`. Group = `agent_console.wiki_search_indexes` (`agent_console_wiki.SEARCH_INDEX_GROUP`);
name = search method id. **The value is a function without arguments**, and that function returns the factory `(root, options)`.

```toml
[project.entry-points."agent_console.wiki_search_indexes"]
"example-inverted" = "agent_console_example_wiki_search:index_factory"
```

At server startup, mod-wiki's host plugin loader reads this group. The method to use is chosen in this order:
the user setting `wiki.search_backend` → the administrator `search.backend` → the administrator `search.fallback`.
**Installing alone does not use it**: you have to write `example-inverted` in one of the first two places.

## Settings example

The user (workspace) settings, `search_backend` in the *Wiki* section of the settings screen:

```yaml
wiki:
  search_backend: example-inverted
```

Or change the default for all users with the administrator settings (`modules.options.mod-wiki.search`):

```yaml
modules:
  options:
    mod-wiki:
      search:
        backend: example-inverted
        fallback: scan          # the method to use when this one is unavailable (empty = no index)
        tokenizer: whitespace   # this example picks the term rule from the name table in data/defaults.json
        index_options:          # search method name -> options only that method receives
          example-inverted:
            token_pattern: "[\\w-]+"   # gives the term regular expression directly (takes precedence over tokenizer)
```

| Option | Default (`data/defaults.json`) | Meaning |
| --- | --- | --- |
| `tokenizer` | `whitespace` | Term rule name (`whitespace`=`\S+`, `word`=`\w+`). An unknown name falls back to the default |
| `token_pattern` | none | Gives the regular expression that extracts terms directly (rejected when it matches the empty string) |
| `case_insensitive` | `true` | Ignore case (mod-wiki fills it from the wiki syntax value) |
| `max_results`, `max_terms`, `max_term_chars`, `max_body_chars`, `snippet_chars` | Wiki library defaults | Search limits |

mod-wiki passes `tokenizer` and `search.index_options.<method>` of the chosen method (such as `token_pattern` in the example above), and overlays
`case_insensitive` (the wiki syntax value) and `max_results` (the administrator `max_search_results`) on top. The last two values
cannot be changed through `index_options`. Without a server, pass the same options to `make_index({...})`.

## Install and remove

Run these from the repository root. Install into the same Python environment as the server. When the server runs in a different virtual environment,
add `--python <path to that virtual environment>` (for example, when you set it with `UV_PROJECT_ENVIRONMENT`, `--python "$UV_PROJECT_ENVIRONMENT"`).

```bash
uv pip install -e examples/extensions/agent-console-example-wiki-search   # install
uv pip uninstall agent-console-example-wiki-search                        # remove
```

Entry points are read at server startup, so **restart the server** after installing or removing.
- Installed and chosen in the settings: the `backend` of wiki search results is `example-inverted`.
- Remove: the name left in the settings is not deleted. The server searches with the fallback method (`search.fallback`) and leaves the server warning
  `wiki.search_degraded` (in the `issues` of the wiki information).
- Keep it installed but not loaded: remove `example-inverted` from the server setting `plugins.enabled` (allow list).

Note: `uv sync` removes packages that are not in the lock file. To sync with the example installed, use `uv sync --all-packages --inexact`.

## Test

The tests run without installing (pytest setting `pythonpath = ["src"]`). The `examples` step of the root `uv run poe check` runs mypy and pytest
with this folder's settings (`uv run poe examples`). Outside the repository, copy only this folder, run `uv sync --find-links <wheelhouse>`
(`uv run poe wheels` in the repository), and then `uv run pytest`.

```bash
cd examples/extensions/agent-console-example-wiki-search
uv run --project ../../.. python -m pytest
```

- `tests/test_wiki_search_contract.py`: all of `agent_console_wiki.testing.WikiSearchContractTests` (partial match, case,
  scores, prefixes and tags, incremental updates, UTF-16 highlights, secret masking, and so on).
- `tests/test_agent_console_example_wiki_search.py`: the entry point declaration, loading with the library loader, no files
  created, highlight ranges, cleaning up the term table for deleted documents, term rule options, and rejecting a wrong `token_pattern`.
- `tests/test_mod_wiki_assembly.py`: a test host + `mod-wiki` assembly. When chosen with the user `search_backend` or the administrator
  `search.backend`, search runs on this index and finds new pages too; when not chosen, the default method; with an unknown name, the
  fallback method + `wiki.search_degraded`; and `token_pattern` in the administrator `search.index_options` reaches the index.

Build your own index the same way: subclass `WikiSearchContractTests` and fill in only `make_index`.
