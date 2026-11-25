# 변경 기록

## 미출시

- REL.8: 선택 포트 `settings.scope_layers`(여러 제공자). `for_lookup(lookup, *, scope=None)` — `scope`(예: 프로젝트 id)를 주면 그 범위 층의 공통 첨부(`resources[]`)도 의존에 넣는다. 생성자 인자 `scopes`(범위 id → 층)·`scope_layers`. 공개 `SCOPE_LAYERS`·`ScopeLayersSource`.
- FU.22: `TeamExportDependencies.for_lookup(lookup)` — 같은 디스크립터·공통 설정으로 다른 정의 저장소(프로젝트 공간)에서 읽는 계산. `mod-exports`가 프로젝트 공간에서 내보낼 때 쓴다.

## 0.1.0

- 처음 만듦(scripts/pkgkit 템플릿 `link`).
- `apps/server`의 `exports.dependencies` 제공(`TeamExportDependencies`)을 옮겼다(3R.12, L10).
