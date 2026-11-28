# Changelog: @agent-console/schema-form

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). A change that breaks the version
range of an internal dependency bumps the other package's version and is recorded here.

## [Unreleased]
- Plural (0.2.2): new message `advancedErrorCountOne`, used when the error count is 1 ("1 error").
- Translated example text (0.2.1): `translateSchema` also passes a string `x-ui.example` through `translate` (non-string examples stay data), so the example hint and the fill-in value follow the display language.
- Messages (0.2.0): moved the default messages to `src/locales/ko.json` (`DEFAULT_MESSAGES` is still ko) and added `en.json`. Subpath exports `./locales/ko` and `./locales/en`. New optional prop `translate?: (text: string) => string` (applied to schema titles and descriptions, `x-ui` when, group titles, units, choice names, uiSchema `ui:title` and so on; by default text is unchanged), and the public `translateSchema`, `translateUiSchema` and `TranslateText`. Added tests for matching keys and placeholders and for no Korean string literals in the source. The public API only grew and the default behavior is the same.
- `x-ui` rendering (required chip, description, example, default value, unit, advanced collapse), the `xui`, `advancedStorageKey` and `compactProvenance` props, and new message keys.
- `hideRootTitle` prop: hides the title of the top-level object (when an outer panel has its own heading). Default false.

## [0.1.0]
- First release.
