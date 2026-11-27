# Changelog: @agent-console/wiki-view

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). A change that breaks the version
range of an internal dependency bumps the other package's version and is recorded here.

## [Unreleased]
- Messages (0.2.1): `SyntaxValueTree` passes its own `syntax.source.label` / `syntax.source.tip` texts to the source badge (new keys in `ko.json` and `en.json`), so the badge no longer falls back to the Korean defaults of `markdown-doc` in another language.
- Locale (0.2.1): `PageTree` (and `buildTree`'s `locale` option), `LinkList`, and `LintTable` take an optional `locale` (BCP 47, normally the display language) for name/code sorting. The default is `"en"` (`DEFAULT_LOCALE` in `tree.ts`) instead of a fixed Korean locale.
- Messages (0.2.0): moved the default messages to `src/locales/ko.json` (`defaultMessages` is still the Korean table) and added `en.json`. New subpath exports `./locales/ko` and `./locales/en` (`messages={en}`). Depends on `@agent-console/markdown-doc` `^0.2.0` for `flattenMessageTree`. Added tests for matching keys and placeholders and for no Korean string literals in the source. The public API only grew and the default behavior is the same.
- `styles.css`: added `line-height` to the `font-size: var(--ac-text-xs|sm)` rules, and replaced `--ac-shadow-md` (not defined) with `--ac-shadow-1`. The `--ac-wiki-*` tokens are defined in `ui/tokens.css`.

## [0.1.0]
- First release.
