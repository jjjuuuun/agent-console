# Changelog: @agent-console/memory-view

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). A change that breaks the version
range of an internal dependency bumps the other package's version and is recorded here.

## [Unreleased]
- Locale (0.2.1): `groupScopes` takes `options.locale` and `MemoryScopeTree` a `locale` prop for sorting scope labels; `MemoryEntryMeta` takes `locale` for the exact byte count. Defaults are `"en"` / `"en-US"` instead of a fixed Korean locale.
- Messages (0.2.0): moved the default messages to `src/locales/ko.json` (`defaultMessages` is still the Korean table) and added `en.json`. New subpath exports `./locales/ko` and `./locales/en` (`messages={en}`), plus `flattenMessageTree` and the `MessageTree` type. Added tests for matching keys and placeholders and for no Korean string literals in the source. The public API only grew and the default behavior is the same.

## [0.1.0]
- First release: the scope tree, the entry table (virtual list, server sorting), the editor (saving held while composing), info, the version list and comparison, cleanup preview, the sort menu, and the pure functions groupScopes, scopeLabel, visibleScopes and formatAuthor.
