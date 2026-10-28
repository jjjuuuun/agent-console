# @agent-console/chat

채팅 **표현** 패키지: 메시지 목록, 입력창, 상호작용 카드. 네트워크·라우터·저장소를 모른다.
데이터와 콜백은 props, 문구는 `messages`(부분 객체)로 받는다. 다른 TS 패키지는 import하지 않는다(`@agent-console/contracts` 타입만).

## 최소 사용
이 블록은 `test/readme.test.ts`와 같고, 테스트가 실제로 실행한다(`pnpm pkg-lint`가 일치를 검사).

```ts readme
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { Composer } from "@agent-console/chat";

const html = renderToStaticMarkup(createElement(Composer, { value: "안녕", onChange: () => {}, onSend: () => {} }));
```

## 설치 / 스타일
워크스페이스 의존으로 추가(react 19 필요). 앱 진입점에서 한 번:
```ts
import "@agent-console/ui/tokens.css";
import "@agent-console/chat/styles.css";
```
색·간격은 전부 `--ac-*` 토큰이고, 버튼은 `.ac-btn`, 상태는 `.ac-status-box[data-status]` 클래스 약속만 쓴다.

## 최소 사용 예
```tsx
<MessageList turns={turns} replyDisplay="separate" agentView={(id) => ({ name: id })}
  renderInteraction={(i, d) => <InteractionCard interaction={i} descriptor={d} onRespond={respond} now={nowSec} />} />
<Composer value={text} onChange={setText} onSend={send} />
```

## 공개 API
- `MessageList` / `TurnView` / `ReplyGroup` / `ProgressStrip` / `Markdown`: 답변 표시 `separate | merged | final_only`(모르는 값은 `separate`), 중간 결과 접기, 스트리밍 캐럿, 대기열 행(`held` 항목은 멈춤 칩 + [실행]/[취소]/[입력창으로 가져오기], 행 포커스에서 Enter/Delete), `resumed_from` 턴의 이어 가기 칩(바로 앞 턴을 이어 간 턴은 같은 사용자 메시지를 다시 그리지 않음), `renderTurnNotice`로 앱이 턴 푸터 위에 알림(끊긴 턴의 이어 가기 배너 등)을 끼움, 진행 줄(방식 라벨은 앱이 전달), 맨 아래 붙어 있을 때만 따라가기.
- `Composer`: 제어형. 전송 키(`enter` 기본 / `ctrl_enter`), **한글 IME 조합 중·직후 Enter 무시**. 답변 모드: `answerTarget`(+`describedBy`), `answerMode`, `onSwitchToMessage`, `onSwitchToAnswer`, `onSendAsMessage`(Ctrl+Shift+Enter, 모드는 바꾸지 않음). 띠는 두 칸 토글 `[답하기 | 새 메시지]`(`radiogroup`, `Alt+Shift+A`). 답변 모드가 아닐 때 안내는 `placeholderHint`.
- `InteractionCard`: 렌더러는 디스크립터 `ui_hints.renderer` 이름으로 `defaultRenderers`(`choices`·`permission`·`review`) + `renderers` prop에서 찾는다. 표에 없으면 `renderFallback`(앱이 SchemaForm 주입), 없으면 내장 JSON 폴백. 종류 id는 쓰지 않는다. `answerVia="external"`이면 입력 요소·제출 버튼 없이 질문과 힌트만 그린다(`RendererProps.readOnlyInput`). 답 입력칸이 입력창인지 카드인지는 순수 함수 `resolveAnswerSurface`(디스크립터 필드와 payload·response_schema 모양만 봄)가 정한다. 카드 상태는 `interaction` prop으로만 바뀐다(낙관적 갱신 없음). `onRespond`가 reject되면 오류 영역에 표시.
- 새 렌더러: `RendererComponent`(`RendererProps` 받아 `onSubmit(response)` 호출, 선택적으로 정적 `summarize`).
- 결정 버튼 모양: `ui_hints{color, icon, dashed}`. `color`는 `tokens.md` 5.5 토큰 이름만(`DECISION_COLOR_TOKENS`), 그 외는 무시.
- `now`는 **epoch 초**(계약의 `created_at` 단위)로 주입한다.

## 진행 줄 중첩 표시 (5R.16)
`ProgressStep`의 선택 필드(전부 앱이 이벤트에서 만든 데이터이며 컴포넌트는 종류를 모른다): `indent`(0 이상 정수, 화면 최대 4단계 × `--ac-progress-indent`), `badge`("별도 세션" 등), `iterationLabel`/`callLabel`("2회차"/"호출 2"), `tone: "warning"`(글자 `▲` + 테두리), `hint`(툴팁), `child: {runId, href, nodeLabel, progress?}`, `children`.
- `children`이 있는 칩은 칩 본문(`Enter`/`Space`, `aria-expanded`)으로 접고 편다. 기본 접힘, 접힌 칩은 `노드 2/5`(`child.progress`가 있을 때만)와 `현재: …`(실행 중인 후손)를 보인다. 자식 실행 링크는 행 끝의 `external-link` 아이콘 별도 링크(`child.href`, `onOpenChild`)다.
- 제어: `expandedStepKeys` + `onStepToggle(key, expanded)`. 생략하면 내부 상태로 사용자의 선택을 유지한다.
- "진행 N단계"와 8개 초과 규칙(최근 3개 + "…외 N단계")은 후손까지 편 전체 목록 기준이다(`flattenSteps`).
- 후손 칩의 실제 들여 쓰기는 `max(자기 indent, 부모 indent + 1)`.
- `TurnView`·`MessageList`의 `onOpenChildRun(runId)`가 자식 실행 아이콘 링크를 받는다.

## 의존성 (무엇을 / 왜 / 대안)
- `react-markdown` + `remark-gfm`: 마크다운 표시. 원시 HTML을 렌더하지 않고(텍스트 이스케이프), http(s) 링크만, 이미지는 alt 텍스트만. 직접 파서를 만들면 보안·유지보수 부담이 커서 채택. 대안: `markdown-to-jsx`, `marked` + DOMPurify.

## 테스트
`pnpm test`
