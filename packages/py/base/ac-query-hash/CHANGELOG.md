# 변경 기록

## 0.1.0

- 처음 만듦(scripts/pkgkit 템플릿 `base`).
- `query_hasher(mode, salt=)`·`QueryHasher`·`QueryHashModes`·`QUERY_HASH_MODES` — `ac-memory`에 있던
  검색어 해셔를 옮겨 `ac-memory`·`ac-wiki`가 함께 쓴다(FU.12). 검색어 인코딩은 `surrogatepass`.
- `query_hasher_from_env(mode, salt_env=, environ=)` — 설정(방식 + 솔트 환경변수 이름) → 해셔.
