# 변경 기록: @agent-console/chat

형식은 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/)를 따른다. 사내 의존 범위를 깨는 변경은 상대 패키지 버전을 올리고 여기에 적는다.

## [미출시]
- 되묻기 답 입력칸 하나로(5.7R.40, screen-chat §10): `resolveAnswerSurface`·`answerViaOf`·`answerCardIds` 공개. `InteractionCard`에 `answerVia`·`answerPaused`·`onDraftChange`, `RendererProps`에 `readOnlyInput`·`onDraftChange`(선택 렌더러·내장 폴백이 따름). `Composer` 답변 모드 띠를 두 칸 토글로(`Alt+Shift+A`, `aria-describedby`, 전환 낭독), `placeholderHint` 추가, `pendingHint`는 호환용(deprecated). 문구 키: `ComposerMessages`의 `answerPlaceholder`·`answer`(문자열)·`answeringTo`·`switchToMessage`·`messageMode`·`switchToAnswer`를 `answer.*` 묶음으로 옮기고 지움, `InteractionMessages.answer` 추가. Ctrl+Shift+Enter는 `onSendAsMessage`만 부른다(없으면 아무 일도 없음).
- 채팅 턴 재디자인(5.2R.21, ux-overhaul §7): 메시지 영역(`MessageList`·`TurnView`·`ReplyGroup`·`ProgressStrip`)의 인라인 스타일을 `styles.css`의 `ac-chat-*` 클래스(토큰만 사용)로 옮김. 내 메시지는 오른쪽 말풍선("나" 라벨 없음, 시각·복사·다시 보내기 아이콘 단추, 호버/포커스에서 표시). 진행 정보는 한 줄 요약("지금: …") + 펼치면 트리, 소요 1초 미만은 숨김(`showDuration` 공개). 자식 실행 링크는 아이콘 하나, 답변 머리의 실행 상세 링크 제거(푸터에 턴당 하나), 최종 답변은 카드 없음. 턴 `tabindex=0`·`↑↓`/`C`/`R`/`Alt+Enter`. `TurnView`·`MessageList`에 `formatTime`, 문구 `yourMessage`·`copyReply`·`progressNow`·`progressSummaryDuration`·`childOpenTip` 추가, `progressSummary`는 `{duration}`을 더 이상 쓰지 않음. 상호작용 카드·입력창의 인라인 스타일은 이번에 옮기지 않음.
- 진행 줄 중첩 표시(5R.16): `ProgressStep`에 `indent`(정수)·`badge`·`iterationLabel`·`callLabel`·`tone`·`child`·`children`·`hint` 추가, 칩 접기·펴기(`expandedStepKeys`/`onStepToggle`), 자식 실행 링크(`onOpenChild`/`onOpenChildRun`), 후손까지 센 단계 수·8개 초과 요약. `flattenSteps`·`visibleSteps`·`currentStepLabel` 공개. 기존 단계(`indent` 0|1, 새 필드 없음)의 표시는 같다.

## [0.1.0]
- 처음 만듦.
