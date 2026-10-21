# @agent-console/schema-form

JSON Schema(+ uiSchema)와 값을 받아 입력 폼을 그리는 React 컴포넌트. @rjsf/core v6 위의 얇은 래퍼이며
API·앱·그래프·전역 상태(fetch, WebSocket, localStorage)를 쓰지 않는다. 필드·순서·라벨·기본값은 전달받은 스키마가 정한다.
`@agent-console/ui` 등 다른 패키지를 import하지 않는다. 공통 모양은 CSS 변수 `--ac-*`와 유틸 클래스 이름으로만 공유한다.

## 최소 사용
이 블록은 `test/readme.test.ts`와 같고, 테스트가 실제로 실행한다(`pnpm pkg-lint`가 일치를 검사).

```ts readme
import { getDefaultValue } from "@agent-console/schema-form";

const schema = { type: "object", properties: { name: { type: "string", default: "새 이름" } } };
const value = getDefaultValue(schema);
```

## 설치
저장소 안에서는 `pnpm install`이 연결한다. 저장소 밖에서는 tarball(`pnpm pack:all` → `dist/npm`)을 설치한다: `npm install ./agent-console-<이름>-<버전>.tgz`
`react`, `react-dom`(^19)은 peerDependency다.

## 최소 사용 예
```tsx
import { SchemaForm, getDefaultValue } from "@agent-console/schema-form";
import "@agent-console/schema-form/styles.css"; // --ac-* 변수는 앱이 tokens.css로 제공(없으면 폴백 값)

const schema = { type: "object", properties: { name: { type: "string", title: "이름" } } };

function Panel() {
  const [value, setValue] = useState(() => getDefaultValue(schema));
  return (
    <SchemaForm
      schema={schema}
      uiSchema={{ name: { "ui:widget": "textarea" } }}
      value={value}
      onChange={setValue}                         // 사용자 편집 때만 호출
      errors={[{ path: "/name", message: "필수" }]} // 서버 오류(JSON Pointer)
    />
  );
}
```

props: `schema`, `uiSchema`, `value`, `onChange`, `errors`, `disabled`, `readonly`, `idPrefix`, `focusPath`,
`customWidgets`(`ui:widget` 이름 → 컴포넌트, props는 `SchemaFormWidgetProps`), `customFields`(`ui:field` 이름 → 컴포넌트, props는 `SchemaFormFieldProps` — 키-값 맵·첨부 목록처럼 객체·배열 값 전체를 한 컴포넌트가 그릴 때. 출처 표시 행 안에서도 동작), `validateOn`(`blur`|`change`|`submit`),
`rawJsonToggle`, `messages`(한국어 기본값 부분 덮어쓰기), `className`.
해석할 수 없는 스키마(`true`, `{}`)나 렌더 예외는 원시 JSON 편집기로 대체된다.

## 출처 표시(선택, R12.3)
설정 층(공통/팀/에이전트/노드 등)이 겹치는 값을 편집할 때 쓴다. `provenance` 또는 `disabledPaths`를 주면 켜지고, 없으면 위 동작 그대로다.
층 id·이름은 코드에 없으며 `layers`(낮은 우선순위가 앞) 데이터로만 받는다. 경로는 모두 JSON Pointer다.

| prop | 설명 |
| --- | --- |
| `layers` `{id,label}[]` / `editLayerId` | 층 목록과 지금 편집 중인 층. 배지 색 슬롯 = 층 인덱스 mod 6(`--ac-layer-1..6`) |
| `provenance` `{pointer: layerId}` | 잎 값별 출처(서버 `Resolved.provenance`). 객체 행은 하위 출처를 모아 "혼합 N층" 배지 |
| `effectiveValue` | 상속 값을 보여 주기 위한 유효 값. `value`는 이 층 값만 |
| `layerValues` `{layerId: value}` | 배지 클릭 팝오버 "값이 정해지는 과정"(`onOpenLayer`가 있으면 줄이 버튼) |
| `onOverride(path)` / `onInherit(path)` | [이 층에서 덮어쓰기·지정] / [↺ 상속으로 되돌리기]. 앱이 `value`를 바꾼다. 입력을 비워도 `onInherit`은 호출되지 않는다 |
| `disabledPaths` `{pointer: 사유}` | 적용 안 되는 필드(하위 포함): 회색 + 자물쇠 + 사유, 입력·버튼 비활성 |
| `fieldWarnings` / `mergeNotes` | 필드 아래 경고 문구 / 라벨 옆 칩 문구(문구는 앱이 정함) |
| `renderProvenanceBadge(info)` | 배지 렌더 주입(예: `@agent-console/ui`의 `ProvenanceBadge`). 이 패키지는 다른 `@agent-console/*`를 import하지 않으므로 내장 배지가 기본 |

- `onChange`는 **이 층의 값만** 돌려준다(상속 값 미포함). 지우면 문자열은 `""`, 그 외는 `null`로 남고 키는 유지된다.
- 상태: `set`(편집 가능 + ↺), `inherited`(읽기 전용 스타일 + 덮어쓰기), `default`(읽기 전용 + 지정). 읽기 전용은 행의 `<fieldset disabled>`로 구현한다.
- `Alt+Enter`: 포커스된 필드의 덮어쓰기/되돌리기 토글. 덮어쓰기 후 편집 가능해지면 입력으로 포커스가 이동한다.
- 배열은 통째로 하나의 값(교체 병합)이라 배지 하나이고 원소 출처(`/tags/0`)는 모아서 본다.

## 스키마 `x-ui` 렌더 (5.2R.18)
스키마의 `x-ui`(`tier`·`when`·`example`·`group`·`group_title`·`order`·`unit`·`enum_labels`(enum 값 → 화면 라벨))를 읽어 그린다. 필드 이름·종류 id는 코드에 없다.
- 기본 필드 위, 고급 필드는 "고급 설정 (N)" 접힘 영역(펼침은 `advancedStorageKey`로 기억, 오류·`focusPath`가 있으면 자동 펼침, "지정 N" 칩).
- 필드마다 필수 칩, 설명 한 줄, 단위 접미사, 예시(빈 칸일 때 클릭하면 채움), 기본값, "바꾸는 때"(고급은 항상, 기본은 i 버튼). `readOnly: true`는 텍스트 + 복사 버튼.
- `x-ui.tier`가 없으면 폴백: `required` -> 기본, 객체는 자식 중 기본이 있으면 기본, 기본값 있는 선택 필드 -> 고급, 없는 선택 필드 -> 기본. 고급만 있는 폼은 접지 않는다.
- `xui={false}`면 기존 rjsf 모양. 출처 표시와 함께 `compactProvenance`를 켜면 지정된 필드만 배지와 되돌리기 아이콘을 보이고, 나머지는 바로 편집(건드리면 이 층에 지정)한다.
- 순수 함수 `readXUi`·`resolveTier`·`splitByTier`는 `src/xui.ts`(공개 export는 아님).

## 폐기 예정 필드 (`deprecated: true`, 2R.8)
- 스키마 속성에 `deprecated: true`가 있으면 **필드 이름을 모른 채** 일반 규칙으로 처리한다(`$defs` 참조 안쪽 포함, 배열 항목 안은 제외).
- 값이 없으면 폼에서 뺀다(스키마와 `required`에서 제거, "숨김 N개" 안내도 두지 않는다). 값이 있으면 그리되 라벨에 `messages.deprecatedChip`, 설명에 `messages.deprecatedNote`를 붙인다. 값은 그대로 편집·삭제할 수 있다.

## 의존성 (무엇을 / 왜 / 대안)
| 패키지 | 버전(설치 시점 npm latest) | 이유 | 대안 |
| --- | --- | --- | --- |
| @rjsf/core | 6.11.0 (peer react >=18, React 19.3 에서 동작 확인) | JSON Schema에서 폼 생성(배열·중첩·oneOf·$ref 처리) | JSON Forms, 직접 구현(비용 큼) |
| @rjsf/utils | 6.11.0 | 기본값 계산·deepEquals 등 유틸 | - |
| @rjsf/validator-ajv8 | 6.11.0 | 클라이언트 검증(ajv8) | validator-ajv6(구버전) |

rjsf 타입은 공개 API에 노출하지 않는다. 엔진 교체 시 이 패키지 내부만 바꾼다.

## 테스트
`pnpm test` (패키지 폴더 또는 루트, Vitest + happy-dom). 테스트는 tokens.css 없이 동작한다.

## 추가 동작
- 배열 추가·삭제·이동·복제 버튼은 패키지 자체 템플릿(문자 아이콘 + 한국어 `aria-label`/`title`, `messages`로 변경)이라 아이콘 폰트(glyphicon)가 필요 없다.
- 스키마가 값의 모양을 정하지 않는 위치(`additionalProperties: true` 자유 객체, 스키마 없는 값 `{}`/`true`)는 해당 값 전체를 원시 JSON 편집기로 그린다(잘못된 JSON은 필드 오류로 표시, 유효할 때만 반영).
