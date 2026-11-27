# Changelog: @agent-console/list-arrange

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). A change that breaks the version
range of an internal dependency bumps the other package's version and is recorded here.

## [0.1.1]
- The default sort locale is now `"en"` (exported as `DEFAULT_LOCALE`) instead of a fixed Korean locale; callers pass
  `locale` (the app passes the display language).

## [0.1.0]
- First release.
