# Changelog: @agent-console/eslint-config

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). A change that breaks the version
range of an internal dependency bumps the other package's version and is recorded here.

## [Unreleased]
- Added `**/dist-*/**` to `DEFAULT_IGNORES`: build output with a separate outDir (`dist-*`) is not linted.
- Added the `agent-console/button-name` rule (error) to the `/react` config: a `<button>` without an accessible name
  (icon only) is not allowed. The rule is in `rules/button-name.js`.

## [0.1.0]
- First release.
