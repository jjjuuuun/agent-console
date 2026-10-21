# 변경 기록

## 미출시

- 5R.13: 토큰 집계는 루트 Run만 센다(`ac-usage.counts_toward_usage`, 자식 Run 이중 집계 방지).

## 0.1.0

- 처음 만듦(scripts/pkgkit 템플릿 `link`).
- `usage.event_query`·`usage.token_rollups`를 `apps/server`에서 옮기고 토큰 집계를 증분 캐시(Run별 이벤트 seq 워터마크, `runs.event` 구독)로 바꿨다(3R.13, design §3R.5).
