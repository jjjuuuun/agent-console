# 변경 기록: @agent-console/wiki-view

형식은 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/)를 따른다. 사내 의존 범위를 깨는 변경은 상대 패키지 버전을 올리고 여기에 적는다.

## [Unreleased]
- Messages (0.2.1, I.13): `SyntaxValueTree` passes its own `syntax.source.label` / `syntax.source.tip` texts to the source badge (new keys in `ko.json` and `en.json`), so the badge no longer falls back to the Korean defaults of `markdown-doc` in another language.
- Locale (0.2.1): `PageTree` (and `buildTree`'s `locale` option), `LinkList`, and `LintTable` take an optional `locale` (BCP 47, normally the display language) for name/code sorting. The default is `"en"` (`DEFAULT_LOCALE` in `tree.ts`) instead of a fixed Korean locale.
- Messages (0.2.0, I.9c): moved the default messages to `src/locales/ko.json` (`defaultMessages` is still the Korean table) and added `en.json`. New subpath exports `./locales/ko` and `./locales/en` (`messages={en}`). Depends on `@agent-console/markdown-doc` `^0.2.0` for `flattenMessageTree`. Added tests for matching keys and placeholders and for no Korean string literals in the source. The public API only grew and the default behavior is the same.
- `styles.css`: `font-size: var(--ac-text-xs|sm)` 규칙에 `line-height`를 더하고 `--ac-shadow-md`(정의 없음)를 `--ac-shadow-1`로 바꿨다. `--ac-wiki-*` 토큰은 `ui/tokens.css`에 정의했다(7R.19).

## [0.1.0]
- 처음 만듦.
