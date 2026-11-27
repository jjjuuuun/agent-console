# Changelog: @agent-console/i18n

Follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). A change that breaks an internal dependency range bumps the other package's version and is noted here.

## [0.2.0]
- Added `ServerText.render(value, parts)`: renders a field made of sentence templates (`text_templates` entry). Every template, nested ones included, must be found in the server catalog; then the translated templates are filled with the values (`{name}` only, integer floats as integers, booleans as `true`/`false`, null as empty, unknown names left as written, unbalanced braces left unchanged) and joined with one space. Otherwise the field value is returned unchanged. Also exported: `fillTemplate`, `TextTemplateLike`, `TextParamValue`.
- Added the server source language: `setSourceLanguage`, `getSourceLanguage`, `chainUntilSource`, the `sourceLanguage` option of `createI18n` and `setLanguage`. `text` and `render` stop their fallback chain at that language, so a translated catalog no longer overrides the original text after switching languages (ko -> en -> ko). `setLanguage` also loads the server catalogs of the fallback languages in front of the source language. `issue` is unchanged.

## [0.1.0]
- First version: `createI18n`, `setLanguage`, `applyServerCatalog`, `resolveLanguage`, default formatters with Korean particles (`particle.*`, `particle.*.only`), `I18nProvider`, `useT`, `useLibMessages`, `useServerText`, `compareCatalogs`, and `@agent-console/i18n/testing`.
