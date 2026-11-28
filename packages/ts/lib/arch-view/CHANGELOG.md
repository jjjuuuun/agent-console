# Changelog: @agent-console/arch-view

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). A change that breaks the version
range of an internal dependency bumps the other package's version and is recorded here.

## [0.2.3]
- Tooltips for truncated text: the cell description and the edge chip label carry `title` with the full text.
- Accessibility: at the summary level the cell button name adds the visible count as its own word when the metric text only contains it inside a word (Korean `5회`), so label-content-name-mismatch passes. The full level adds the same word, so the accessible name is identical at both scales (spec 13-8); a cell with a count in a word (`0회`) now has that number as an extra word in its name.

## [0.2.2]
- Accessibility (axe serious 0): the cell button and list-row accessible names now start with the visible text
  (`cellAccessibleName`, WCAG 2.5.3 label-content-name-mismatch); the scale button name includes the visible percentage.

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
