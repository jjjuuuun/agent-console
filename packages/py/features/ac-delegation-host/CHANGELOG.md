# 변경 기록

## 미출시

- 5.2R.43: 디스크립터 `shares_session=False`(대상은 자기 세션). `failure_text`의 `{code}`·`{message}`는 엔진 가림(`ctx.secrets.redact`)을 건 값만 쓴다(`HostDelegation.failure_text`).

## 0.1.0

- 처음 만듦(scripts/pkgkit 템플릿 `feature`, 5R.9): 위임 방식 `host`(`HostDelegation`·`host_descriptor`·
  `HostDelegationConfig`·`HostDelegationCodes`), entry point `agent_console.delegation_strategies:host`.
