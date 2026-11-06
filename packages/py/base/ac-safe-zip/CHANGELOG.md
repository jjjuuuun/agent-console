# 변경 기록

## 0.1.0

- 처음 만듦(7R.8): `ac-memory` 마크다운 zip 가져오기의 안전 규칙(경로 공격·심볼릭 링크·암호화·압축 폭탄 상한)을 뽑아 `open_zip`·`iter_members`·`read_zip`·`unsafe_archive_path`·`is_symlink`·`ZipLimits`·`ZipLimitError`·`ZipFormatError`로, 고정 바이트 쓰기 `write_zip`.
