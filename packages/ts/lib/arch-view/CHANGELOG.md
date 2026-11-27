# Changelog: @agent-console/arch-view

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). A change that breaks the version
range of an internal dependency bumps the other package's version and is recorded here.

## [0.2.1]
- Locale: `ArchitectureDiagram`, `ArchitectureInfoBar` and `ArchitectureCellList` take an optional `locale` (BCP 47,
  normally the display language) for digit grouping; `formatMetric`/`metricPieces` options, `groupDigits(n, locale)`,
  `abbreviateNumber(n, locale)`, `cellAriaLabel`/`edgeAriaLabel` and `buildEdgeModels` accept it too. The default is
  `DEFAULT_NUMBER_LOCALE` (`"en-US"`).

## [0.2.0]
- Message data: moved the default messages to `src/locales/ko.json` (`defaultMessages` is still Korean) and added
  `en.json`. Subpath exports `./locales/ko` and `./locales/en` (`messages={en}` for English). Added the `checkLayout`
  option `errorsPlaceholder` (the default is the default message `metricErrors` filled with 0, the same result as the
  old hardcoded `오류 0`). The error message for using `useDiagram` outside `ArchitectureDiagram` is in English, and the
  `josa` comparison with `으로` uses code point notation. Added tests that check keys and placeholders match and that
  the source has no Korean strings.

## [0.1.0]
- First release.
