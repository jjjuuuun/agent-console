# 변경 기록

## 미출시

- 5.2R.43: 선택 능력 `RedactorConsumer.use_redactor(redact)`·타입 `Redactor`(판정 근거를 만드는 확장이 앱의 가림 함수를 받는다).
- 5R.13: 선택 능력 `OperatorConsumer.use_operators(provider)`·`OperatorProvider`(연산자를 쓰는 확장이 앱의 연산자 레지스트리를 받는다).

## 0.1.0

- 처음 만듦(5R.8, design §5R.3 X22·§5R.5): `ConditionOperator` 프로토콜·`ValueChecker` 선택 능력,
  레지스트리 로더(entry point `agent_console.condition_operators`, `LoadReport`), `evaluate_conditions`
  (근거 = 계약 `ConditionOutcome`, `actual`은 가린 뒤 자름), `condition_issues`(모르는 연산자 warning,
  값 스키마·연산자 검사 error, 빈 조건 warning), 기본 연산자 10개(디스크립터는 데이터 파일).
