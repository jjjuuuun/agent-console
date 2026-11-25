# 플러그인 공통

"같은 종류 하나 더"는 모두 같은 방식으로 들어온다. 패키지가 entry point로 구현을 알리고, 서버가 시작할 때 그것을
읽어 확장 지점마다 레지스트리에 등록한다. 기본 구현도 같은 길로 등록되므로 플러그인은 기본 구현과 똑같이
다뤄진다. 이 문서는 지점과 상관없이 같은 규칙을 모은다. 지점마다 다른 것(인터페이스, 디스크립터 필드)은
영역 페이지에 있다.

## entry point

```toml
[project.entry-points."agent_console.edge_types"]
"acme.relay" = "acme_console_edges:RelayEdge"
```

- **그룹** = 확장 지점. 그룹 이름은 정의한 패키지의 공개 상수(예: `agent_console_runtime.EDGE_TYPES_GROUP`)와 같다.
  전체 목록과 기본 구현: [entry point 그룹 표](reference.md#entry-point-그룹).
- **이름** = 등록 id. 데이터(팀 구성의 `type`·`kind`, 조건의 `op`, 설정의 출처 id)가 이 이름으로 구현을 찾는다.
  디스크립터가 있는 지점이면 디스크립터 `id`와 같게 둔다.
- **값** = `모듈:속성`. 속성은 다음 중 하나다.
  - 클래스: 서버가 인자 없이 인스턴스를 만든다. 가장 흔한 모양이다.
  - 이미 만든 객체(모듈 수준 인스턴스).
  - 인자 없는 팩토리: 몇몇 지점은 "인자 없는 함수 → 실제 구현을 만드는 함수"를 받는다(예: 위키 검색 색인은
    `(폴더, 옵션) -> 색인`을 돌려주는 함수). 그 모양은 지점의 영역 페이지에 적혀 있다.
- 생성자에서 파일·네트워크·환경변수를 읽지 않는다. 바깥 값은 설정(`config`·옵션)이나 지점이 넘겨주는 문맥으로
  받는다. 그래야 테스트에서 가짜로 바꿀 수 있고 로드가 빠르다.

## 이름과 중복

- 같은 그룹에 같은 이름이 둘이면 하나만 등록된다. 이름이 같은 항목은 값(모듈 경로) 순으로 앞의 것이 쓰이고 뒤의
  것은 `failed`(중복)로 보고된다. 기본 구현의 이름을 덮어쓸 수는 없다.
- 그래서 이름에는 자기 접두사를 붙인다(`acme.relay`). 접두사 없는 이름은 기본 구현이 쓴다.
- 다른 버전을 같은 이름으로 함께 두는 지점(노드 종류의 `type_version` 등)은 그 지점 페이지가 설명한다.

## 로드 시점과 실패

- entry point는 **서버가 시작할 때 한 번** 읽는다. 설치·제거·버전 교체 뒤에는 서버를 다시 시작한다.
- 로드 실패는 서버를 멈추지 않는다. import 오류, 속성 없음, 지점 검사 실패(필요한 메서드·디스크립터 없음), 중복은
  그 항목만 빠지고 결과가 보고된다.
- 결과는 `GET /api/v1/server-info`의 `plugins`에 항목마다 나온다.

| `status` | 뜻 |
| --- | --- |
| `loaded` | 등록됨 |
| `failed` | 읽지 못함. `error`에 이유(예외 이름과 메시지) |
| `skipped` | `plugins.disabled`에 있거나 `plugins.enabled`에 없어 읽지 않음 |
| `disabled` | 명시 모듈 플러그인이 등록했지만 `plugins.disabled`에 있거나 `plugins.enabled`에 없어 뺌 |

`skipped`·`disabled`는 오류가 아니므로 `error`가 비어 있다. 어느 설정 때문인지는 `reason`
(예: `설정 plugins.disabled에 있음`)과 서버 로그에 남는다.

```bash
curl -s http://127.0.0.1:8765/api/v1/server-info      # plugins: [{name, group, loaded, status, reason, error}]
```

## 켜고 끄기

서버 설정 파일(또는 환경변수):

```yaml
plugins:
  disabled: [acme.relay] # 끌 이름(모든 그룹 공통). 나머지는 그대로 읽는다
  enabled: null          # null = 설치된 것 전부. 목록을 주면 그 이름만 읽는다(모든 그룹 공통)
  modules: []            # 설치하지 않은 플러그인 모듈 "패키지.모듈:속성"(아래)
```

- **하나만 끄려면 `plugins.disabled`에 그 이름을 적는다.** 다른 플러그인과 기본 구현은 그대로 읽힌다. 이름은
  entry point 이름(등록 id)이고, `server-info`의 `plugins`에 나오는 `name`과 같다.
- `plugins.enabled`는 **모든 그룹에 함께 걸리는 허용 목록**이다. 기본 구현도 entry point로 들어오므로 목록을 적으면
  기본 구현의 이름도 함께 적어야 한다. 쓸 것만 골라 적을 때 쓴다.
- 둘 다 적으면 `plugins.enabled` 안에서 `plugins.disabled`를 뺀다(제외 목록이 이긴다).
- 두 목록 모두 그룹을 가리지 않는다. 다른 그룹에 같은 이름이 있으면 함께 꺼진다.
- `plugins.disabled`에 설치되지 않은 이름을 적으면 서버는 시작하고, `server-info`의 `warnings`에 `plugins.config`
  경고를 낸다(오타 확인용).
- `plugins.modules` 플러그인이 등록한 항목에도 같은 규칙이 걸린다. 이름은 등록한 key이고, 꺼진 항목은 `group`
  `plugins.modules`, `status` `disabled`로 나온다(entry point 플러그인은 `skipped`).
- 환경변수: `AGENT_CONSOLE_PLUGINS_DISABLED`·`AGENT_CONSOLE_PLUGINS_ENABLED`(쉼표로 구분),
  `AGENT_CONSOLE_PLUGIN_MODULES`.
- 설치하지 않고 시험할 때는 `plugins.modules`에 `"패키지.모듈:속성"`을 적는다. 그 속성은 `register(registries)`
  메서드가 있는 객체 또는 같은 모양의 함수이고, 이름 붙은 레지스트리에 직접 등록한다. 등록은 entry point와 같은
  검사를 거친다. 모듈은 서버의 import 경로에 있어야 한다.
- 서버 모듈(기능 단위)은 플러그인이 아니라 모듈 설정 `modules.enabled`·`modules.disabled`로 켜고 끈다
  ([서버 모듈](modules.md#켜고-끄기)).

## 지운 뒤 남는 데이터

플러그인을 지우거나 끄면 그 이름을 쓰던 사용자 데이터(팀 구성의 노드·연결, 조건, 리소스, 설정의 출처 항목)는
**지워지지 않는다**. 대신:

- 저장 전 검사와 목록 검사가 이슈로 알린다. 코드와 심각도는 지점마다 정해져 있고 영역 페이지에 적는다. 예: 노드
  종류 `unknown_node_type`·연결 종류 `unknown_edge_type`은 오류(그 팀 구성은 실행 전 검사에서 막힌다), 조건 연산자
  `condition.unknown_operator`는 경고(실행은 되고 그 조건 항목만 거짓).
- 모르는 이름이 영향을 주는 범위는 그 부분뿐이다. 다른 팀 구성과 다른 플러그인은 그대로 동작한다.
- 다시 설치하면 데이터를 고치지 않고 그대로 동작한다.

플러그인을 만들 때도 같은 관례를 따른다. 내 플러그인이 다른 확장의 id를 데이터로 받으면, 모르는 id는 예외 대신
자기 접두사의 경고 코드로 알리고 그 부분만 건너뛴다.

## 설정 스키마

지점 대부분은 디스크립터에 `config_schema`(JSON Schema)를 둔다. 웹은 이 스키마로 설정 폼을 그리므로 플러그인은
웹 코드를 쓰지 않는다. 필드마다 다음을 단다.

| 키 | 무엇 |
| --- | --- |
| `title` | 짧은 라벨 |
| `description` | 무엇을 하는지, 왜 바꾸는지 한 문장. 내부 이름을 쓰지 않는다 |
| `x-ui.tier` | `basic`(위쪽에 보임) 또는 `advanced`(접힘) |
| `x-ui.when` | 언제 바꾸는지 한 문장(`basic` 필드는 필수) |
| `x-ui.example` | 빈 칸을 눌렀을 때 채울 예시 값 |
| `x-ui.unit` | 단위(초, 개, MB) |

Pydantic 모델이면 `x_ui()`를 `json_schema_extra`에 넣는다. `lint_schema_help`로 스스로 검사할 수 있다.
스키마 맨 위 `title`·`description`은 폼 머리말로 보이는데, Pydantic은 클래스 이름과 docstring을 그대로 넣는다.
`model_config = ConfigDict(title="...")`로 제목을 주고 docstring은 사용자가 읽는 한 문장으로 둔다(`Attributes:` 같은
코드 문서는 각 `Field(title=..., description=...)`로 옮긴다).

```python
>>> from pydantic import BaseModel, Field
>>> from agent_console_contracts import x_ui
>>> from agent_console_contracts.schema_help import lint_schema_help
>>> class RelayConfig(BaseModel):
...     prefix: str = Field(
...         default="",
...         title="머리말",
...         description="다음 노드에 넘길 때 앞에 붙일 글입니다.",
...         json_schema_extra=x_ui(
...             tier="basic", example="[검토 요청] ", when="넘기는 글을 구분하고 싶을 때 바꾸세요."
...         ),
...     )
>>> lint_schema_help(RelayConfig.model_json_schema())
[]
>>> sorted(i.rule for i in lint_schema_help({"type": "object", "properties": {"n": {"type": "integer"}}}))
['missing-description', 'missing-example', 'missing-tier', 'missing-title']

```

웹이 모르는 `x-ui` 위젯 이름을 쓰면 구조화 값은 JSON 편집으로 바뀌고 안내가 붙는다. 새 위젯이 꼭 필요하면 [웹](web.md).

## 비밀 값

- 비밀(키·토큰)은 설정에 값으로 쓰지 않는다. 사용자는 `secret://이름` 참조를 쓰고, 서버가 환경변수(또는 비밀 공급자
  플러그인)에서 값을 찾아 넘긴다. 참조는 문자열 전체가 `secret://이름`일 때만 풀린다.
- 스키마에서 비밀 필드는 `SecretStr`(또는 `"x-secret": true`)로 표시한다. 화면·설정 보기·응답에서 가려진다.
- 받은 비밀을 로그·이벤트·오류 메시지·예외 문자열에 넣지 않는다. 엔진이 해석한 값은 기록에서 가리지만, 플러그인이
  다른 길로 얻은 값이나 바꾼 값(인코딩·일부 잘림)은 가릴 수 없다.
- 새 비밀 출처(파일·키체인 등)가 필요하면 비밀 값 공급자 지점을 쓴다([실행 백엔드](backends.md)).

## 확장 지점 하나 고르기

| 하고 싶은 일 | 볼 곳 |
| --- | --- |
| 지점 전체 표(등록 종류·기본 구현 수·예제 종류) | [확장 지점 참조](reference.md#확장-지점) |
| 예제 패키지 설치해 보기 | [예제 색인](../../examples/extensions/README.md) |
| 처음 만들기 | [시작하기](getting-started.md) |
