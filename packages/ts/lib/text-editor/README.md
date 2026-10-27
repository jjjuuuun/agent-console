# @agent-console/text-editor

CodeMirror 6 기반 텍스트 편집 컴포넌트 `<TextEditor>`. 마크다운·HTML·JSON 구문 강조. 저장·리소스·API를 모른다(제어형).
다른 `@agent-console/*` 패키지를 import하지 않는다(react는 peer). 색·글꼴은 `--ac-*` CSS 변수(없으면 폴백)를 쓰므로 `@agent-console/ui/tokens.css`가 로드돼 있으면 다크/라이트가 자동으로 따라간다.

## 최소 사용
이 블록은 `test/readme.test.ts`와 같고, 테스트가 실제로 실행한다(`pnpm pkg-lint`가 일치를 검사).

```ts readme
import { jsonParseError } from "@agent-console/text-editor";

const broken = jsonParseError('{"a": ');
const fine = jsonParseError('{"a": 1}');
```

## 설치 / 사용
저장소 안에서는 `pnpm install`이 연결한다. 저장소 밖에서는 tarball(`pnpm pack:all` → `dist/npm`)을 설치한다 (react 19 필요)

```tsx
import { TextEditor } from "@agent-console/text-editor";

<TextEditor
  value={text}
  onChange={setText}            // 사용자 편집(IME 조합 중 포함)만 호출. value prop 반영은 호출 안 함
  language="markdown"           // markdown | html | json | text (모르는 값 = text)
  ariaLabel="본문 편집기"        // 필수
  onSave={save}                 // Ctrl/Cmd+S (조합 중에는 무시)
  maxBytes={1_000_000}
  onTooLarge={(bytes) => warn(bytes)}   // 초과 시 읽기 전용
  onStatus={({ line, col, chars, parseError }) => setStatus(...)}   // json이면 parseError(편집은 막지 않음)
  onCompositionChange={(composing) => setBusy(composing)} // IME 조합 시작 true / 끝 false
  handleRef={ref}               // ref.current.isComposing()
  onCompositionChange={(composing) => setBusy(composing)} // IME 조합 시작 true / 끝 false
  handleRef={ref}               // ref.current.isComposing()
  height="fill"                 // px 숫자 또는 부모를 채움
  messages={{ tooLarge: "크기 제한을 넘어 읽기 전용입니다" }}
/>
```

## 동작 규칙
- 한글 IME: 자동 완성·자동 괄호를 켜지 않고, 조합 중에는 저장 단축키를 처리하지 않는다. `value`가 현재 문서와 같으면 건드리지 않아 커서·조합이 유지된다.
- 조합 상태 API: `onCompositionChange(composing)`는 compositionstart/end에서 상태가 바뀔 때만 부른다. `handleRef`로 받은 `TextEditorHandle.isComposing()`은 같은 값을 돌려준다. 조합 중 검사·저장 같은 부수 작업을 미루려는 소비처(설정 › 구조도, 메모리 편집기)가 쓴다. `onChange`는 조합 중에도 호출된다.
- 탭 키 = 공백 2칸 들여쓰기(`Esc` 후 `Tab`으로 편집기를 빠져나갈 수 있다). 줄 번호, 줄바꿈 기본 켬(`lineWrap`).
- 편집기 요소에 `data-ac-editable`을 달아, 앱 전역 단일 키 단축키 처리기가 무시할 수 있게 한다.
- 공개 API: `TextEditor`, `resolveLanguage(name)`, `jsonParseError(text)`, 타입 `TextEditorHandle`/`TextEditorProps`/`TextEditorStatus`/`TextEditorMessages`/`EditorLanguage`.

## `<TextDiff>` — 읽기 전용 텍스트 비교

```tsx
import { TextDiff } from "@agent-console/text-editor";

<TextDiff
  before={oldText}
  after={newText}
  language="markdown"
  ariaLabel="SKILL.md 비교"
  mode="auto"            // split(나란히) | unified(통합) | auto(폭 < unifiedBelow(900px)면 통합)
  context={3}            // 변경 없는 구간을 접을 때 앞뒤로 남기는 줄 수 (음수 = 접지 않음)
  messages={{ unchangedLines: "변경 없는 $줄", split: "나란히", unified: "통합", toolbar: "보기 방식" }}
/>
```
- 두 문자열만 받는다(저장·API를 모른다). `F3` / `Shift+F3` = 다음/이전 변경 블록(편집기 포커스 시). 줄 번호·`--ac-font-mono`.
- 도구 줄(`showToolbar`)의 전환 버튼은 `aria-pressed`. 접힌 구간은 `@codemirror/merge`의 클릭 위젯이다(키보드로는 펼칠 수 없음 — 접지 않으려면 `context={-1}`).
- 공개 API 추가: `TextDiff`, 타입 `TextDiffProps`/`TextDiffMessages`/`TextDiffMode`.

## 의존성 (무엇을 / 왜 / 대안)
- `@codemirror/state`·`view`·`commands`·`language`: 편집기 코어 — 가볍고 IME 처리가 성숙함. 대안: Monaco(무거움), textarea(구문 강조·확장 부족).
- `@codemirror/lang-markdown`·`lang-html`·`lang-json`: 언어별 구문 강조. 대안: 직접 정규식 강조(유지보수 부담).
- `@codemirror/merge`(MIT): `TextDiff`의 나란히(`MergeView`)·통합(`unifiedMergeView`) 비교와 변경 구간 접기·다음 변경 이동. 이미 쓰는 CodeMirror 계열이라 테마·언어 확장을 그대로 공유한다. 대안: `diff2html`/`react-diff-viewer`(별도 렌더러라 테마·IME·접근성 재작업), 직접 LCS diff 구현(유지보수 부담).
- `@lezer/highlight`: 토큰 태그를 `--ac-*` 색으로 매핑하는 하이라이트 스타일. 대안: 기본 하이라이트(토큰·테마 미연동).

## 테스트
`pnpm test` — `TextDiff`(나란히·통합·전환·접힘·갱신), 값 표시·onChange 구분·readOnly·maxBytes·Ctrl+S·IME(composition)·자동 괄호 없음·onStatus.
