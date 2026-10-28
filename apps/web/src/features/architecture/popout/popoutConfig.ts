/** 구조도 분리 창의 데이터 표(경로·창 모양·저장 키·점검 간격). 코드에 흩어 두지 않는다. */
export const ARCH_POPOUT = {
  /** 분리 창 라우트(앱 셸 밖, 같은 앱). 쿼리: `key`(범위 키), `scope`(JSON 범위 인자) */
  path: "/popout/architecture",
  queryKey: "key",
  queryScope: "scope",
  /** `window.open` 창 모양 */
  features: "popup=yes,width=1280,height=860",
  /** 동기화 채널 이름 접두(범위 키가 뒤에 붙는다) */
  channelPrefix: "ac.arch.sync.",
  /** 분리 창이 닫혔는지 확인하는 간격(ms). `bye` 메시지를 못 보내고 닫힌 경우(강제 종료)를 잡는다. */
  closedPollMs: 1000,
  /** 분리 창이 열려 있는지 묻는 `ping`에 답이 오기를 기다리는 시간(ms) */
  pingWaitMs: 400,
  storage: {
    /** "분리해서 보기"를 기억한다. 값 `1`이면 구조도 자리에 [새 창으로 분리]를 먼저 보인다. 범위 종류(세션·실행)별로 따로 둔다. */
    prefer: "ac.arch.popout.prefer",
  },
} as const;

/** 범위 종류별 저장 키 */
export const preferKey = (kind: string): string => `${ARCH_POPOUT.storage.prefer}.${kind}`;
