# 변경 기록

## 미출시

- 4R.18: 옛 최상위 `exports` 읽기 호환 제거. `home` 기본값을 옛 `imports.home`에서 넘기지 않는다(자기 옵션, 생략 시 HOME·USERPROFILE).

## 0.1.0

- 처음 만듦(scripts/pkgkit 템플릿 `module`).
- `apps/server`의 `/exporters`·`/exports/*`와 내보내기 서비스 조립(카탈로그 = `definitions.lookup` + `exports.dependencies`)을 옮겼다(3R.10). 설정 `modules.options.mod-exports`(옛 `exports.*`, `home`·`expose_paths` 추가).
