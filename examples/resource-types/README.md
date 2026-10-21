# 선언형 리소스 종류 예제

코드 없이 **YAML 파일 하나**로 리소스 종류(확장 지점 X14)를 추가하는 예제(R0·R10.4).
설치할 패키지가 없다 — 파일을 workspace 폴더에 넣으면 생기고, 지우면 사라진다.

| 파일 | 종류 id | 하는 일 |
| --- | --- | --- |
| `prompt-snippet.yaml` | `prompt-snippet` | 마크다운 본문 하나를 지침 칸(`instructions`)에 `## <이름>` 제목과 함께 넣는다. 설정 `tone`(enum) |

## 최소 데이터

```yaml
id: prompt-snippet
title: 프롬프트 조각
config_schema: {type: object, properties: {tone: {type: string, enum: [formal, casual]}}}
content: {media_types: [text/markdown], editor: markdown}   # 문서형(본문 편집기)
contributes:
  - slot: instructions
    template: "## {title}\n{content}"
```

- `contributes[].slot`: 실행 묶음 칸 이름(문자열, 고정 목록 아님). 백엔드가 받지 않는 칸이면 묶음 미리보기·검증이 `resource.slot_unsupported`로 알린다.
- 치환 변수: `id`·`name`·`description`·`title`(기본 = 이름)·`content`(본문) + config 최상위 키.
- 전체 형식: `agent_console_resources` 패키지의 `_declarative` 모듈 문서(`DeclarativeTypeSpec`, `value`·`raw`·`combine` 등).

## 등록·제거

```bash
cp examples/resource-types/prompt-snippet.yaml <workspace>/resource-types/   # 등록
rm <workspace>/resource-types/prompt-snippet.yaml                            # 제거
```

선언형 종류는 서버 시작 때 읽으므로 **서버를 재시작**한다.
- 등록: `GET /api/v1/resource-types`에 `prompt-snippet`(`declarative: true`)이 나오고, 리소스 화면 "새 리소스" 종류 목록에 "프롬프트 조각"이 보인다.
- 제거: 목록에서 사라진다. 이 종류로 만든 리소스는 지워지지 않고 검증이 `resource.unknown_type` 경고로 알린다.
- 같은 id가 플러그인 종류와 겹치면 선언형 파일 쪽이 로딩 실패(`LoadReport` `failed`)로 보고되고 등록되지 않는다.

## 테스트

`tests/test_resource_type_examples.py`가 이 폴더의 모든 `*.yaml`을 서버와 같은 로더(`load_declarative_types`)로 읽고 기여 결과를 확인한다.
루트 `uv run poe check`가 수집한다. E2E `08-extension`의 "리소스 종류" 시나리오는 이 파일을 workspace에 복사해 쓴다.
