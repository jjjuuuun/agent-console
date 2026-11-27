# Changelog

## 0.1.0

- First release: the safety rules of the `ac-memory` markdown zip import (path attacks, symbolic links, encryption and
  zip bomb limits) are extracted into `open_zip`, `iter_members`, `read_zip`, `unsafe_archive_path`, `is_symlink`,
  `ZipLimits`, `ZipLimitError` and `ZipFormatError`, plus `write_zip` for byte-stable writes.
