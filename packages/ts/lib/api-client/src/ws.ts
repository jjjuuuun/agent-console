import type {
  ConversationSummary,
  ErrorInfo,
  Interaction,
  LogsIngestedPayload,
  RunEvent,
  WsClientMessage,
  WsServerMessage,
} from "@agent-console/contracts";
import {
  WS_AUTH_CLOSE_CODES,
  WS_CLOSE_FORBIDDEN,
  WS_CLOSE_UNAUTHORIZED,
} from "@agent-console/contracts";
import type { MemoryChanged } from "@agent-console/contracts/memory";
import { resolveToken, type TokenSource } from "./token";

/** 브라우저 `WebSocket`(또는 `ws` 패키지, 테스트용 가짜)이 만족하는 최소 모양. */
export interface WebSocketLike {
  readonly readyState: number;
  send(data: string): void;
  close(code?: number, reason?: string): void;
  /* eslint-disable @typescript-eslint/no-explicit-any -- DOM 이벤트 타입과 호환시키려고 any */
  onopen: ((ev: any) => void) | null;
  onmessage: ((ev: any) => void) | null;
  onclose: ((ev: any) => void) | null;
  onerror: ((ev: any) => void) | null;
  /* eslint-enable @typescript-eslint/no-explicit-any */
}

/** URL로 소켓을 만드는 함수. 기본값은 `(url) => new WebSocket(url)`. */
export type WebSocketFactory = (url: string) => WebSocketLike;

// close 코드 상수는 계약이 단일 소스다. api-client 공개 이름은 그대로 유지한다.
export { WS_AUTH_CLOSE_CODES, WS_CLOSE_FORBIDDEN, WS_CLOSE_UNAUTHORIZED };

/** `WebSocket.OPEN`. */
const WS_OPEN = 1;

export type ConnectionStatus = "idle" | "connecting" | "open" | "reconnecting" | "closed";

/** 재접속 대기 시간: `min(maxMs, initialMs * factor^시도) * (1 - jitter * random())`. */
export interface BackoffOptions {
  initialMs?: number;
  maxMs?: number;
  factor?: number;
  /** 0~1. 0이면 지터 없음. */
  jitter?: number;
}

export interface TimerApi {
  setTimeout(fn: () => void, ms: number): unknown;
  clearTimeout(handle: unknown): void;
}

export interface WsClientOptions {
  /** 서버 주소. `http(s)://` 또는 `ws(s)://`. `/ws`는 클라이언트가 붙인다. */
  baseUrl: string;
  /** 연결 쿼리 `?token=`. 재접속 때마다 다시 읽는다. */
  token?: TokenSource;
  /** WebSocket 구현 주입. 기본은 전역 `WebSocket`. */
  webSocket?: WebSocketFactory;
  backoff?: BackoffOptions;
  /** 타이머 주입(테스트에서 가짜 시계). */
  timers?: TimerApi;
  /** 0~1 난수 주입(백오프 지터). */
  random?: () => number;
  /** 요청 상관 id 생성기. 기본은 `c1`, `c2`, … */
  nextId?: () => string;
  /**
   * 특정 요청에 귀속되지 않는 서버 `error`, 그리고 핸들러가 던진 예외(`code: "handler_error"`).
   * 이 콜백이 던진 예외는 무시한다.
   */
  onError?: (error: ErrorInfo, requestId?: string) => void;
  /**
   * 연결이 이 시간(ms) 동안 유지되면 백오프를 초기화한다(기본 10000).
   * 첫 메시지를 받아도 초기화된다. 열자마자 서버가 닫는 경우 재시도 간격이 계속 늘어난다.
   */
  stableMs?: number;
  /** 이 close 코드로 닫히면 재접속하지 않고 `closed`가 된다(기본: `WS_AUTH_CLOSE_CODES` = 인증·Host 검사 실패). 빈 배열이면 항상 재접속. */
  noReconnectCloseCodes?: readonly number[];
}

export interface SubscribeOptions {
  /**
   * 이 seq 다음부터 받는다(예: `RunSnapshot.last_seq`). 그 이하 seq는 버린다.
   * 같은 토픽의 두 번째 이후 구독에서는 무시된다.
   */
  sinceSeq?: number;
  /**
   * 이 구독 요청(재접속 때 다시 보내는 요청 포함) 때문에 서버가 보낸 `error`.
   * 같은 토픽의 두 번째 이후 구독에서는 무시된다.
   */
  onError?: (error: ErrorInfo) => void;
}

export interface Subscription {
  readonly topic: string;
  unsubscribe(): void;
}

export interface WsClient {
  readonly status: ConnectionStatus;
  /** 연결을 시작한다. 구독을 열면 자동으로 호출되므로 보통 직접 부를 필요는 없다. */
  connect(): void;
  /** 재접속을 멈추고 소켓을 닫고 모든 구독을 정리한다. 이후 `connect()`로 새로 시작할 수 있다. */
  close(): void;
  onStatus(listener: (status: ConnectionStatus) => void): () => void;
  /**
   * 토픽 구독. `run:<id>` 토픽은 그 Run의 `run.event`를 `handler`에 한 번씩, seq 순서대로 준다.
   * 재접속하면 마지막으로 받은 seq 다음부터(`since_seq`) 서버가 재생하며 이미 받은 seq는 버린다.
   * 이미 지난 seq(순서가 뒤바뀌어 늦게 온 이벤트 포함)는 버린다.
   * 같은 토픽을 여러 번 구독하면 소켓 구독은 하나로 합쳐지고, 늦게 붙은 쪽은 이후 이벤트부터 받으며
   * 두 번째 이후 구독의 `sinceSeq`와 `onError`는 무시된다.
   */
  subscribe(topic: string, handler: (event: RunEvent) => void, options?: SubscribeOptions): Subscription;
  /**
   * `conversation:<id>` 토픽: 새 턴·제목·상태·대기 중 상호작용 수가 바뀔 때 `conversation.updated`의 요약을 준다.
   * 재접속하면 자동으로 다시 구독한다(재생 없음 — 앱이 REST로 다시 읽는다).
   */
  subscribeConversation(
    conversationId: string,
    handler: (conversation: ConversationSummary) => void,
    options?: Pick<SubscribeOptions, "onError">,
  ): Subscription;
  /**
   * `interactions` 토픽: 구독 직후 현재 대기 목록을 하나씩, 이후 상태가 바뀔 때마다 `interaction.updated`를 준다
   * (모든 대화, 사이드바 배지용). 재접속하면 서버가 대기 목록을 다시 보낸다.
   */
  subscribeInteractions(
    handler: (interaction: Interaction) => void,
    options?: Pick<SubscribeOptions, "onError">,
  ): Subscription;
  /**
   * `logs` 토픽(로그 수집 알림): 새 이벤트가 색인에 들어올 때마다 `logs.ingested`의 payload를 준다
   * (구독 직후에는 아무것도 보내지 않는다. 어느 세션이 바뀌었는지는 모르므로 앱이 다시 조회한다).
   * 재접속하면 자동으로 다시 구독한다(재생 없음).
   */
  subscribeLogs(handler: (ingested: LogsIngestedPayload) => void, options?: Pick<SubscribeOptions, "onError">): Subscription;
  /**
   * `memory.changed` 토픽(공유 메모리): 항목 하나가 바뀔 때마다 변경 알림(본문 없음)을 준다.
   * 구독 직후에는 아무것도 보내지 않는다(앱이 REST로 처음 불러온다). 재접속하면 자동으로 다시 구독한다(재생 없음).
   */
  subscribeMemory(handler: (changed: MemoryChanged) => void, options?: Pick<SubscribeOptions, "onError">): Subscription;
  /** `subscribe("run:<runId>", …)`의 단축. */
  subscribeRun(runId: string, handler: (event: RunEvent) => void, options?: SubscribeOptions): Subscription;
  /** 서버가 보낸 모든 메시지(중복 제거 전, 원본). `graph:` 토픽 등 전용 핸들러가 없는 메시지용. */
  onMessage(listener: (message: WsServerMessage) => void): () => void;
}

interface TopicEntry {
  topic: string;
  lastSeq: number;
  handlers: Set<(event: RunEvent) => void>;
  onError: ((e: ErrorInfo) => void) | undefined;
}

/** run 토픽이 아닌 토픽(`conversation:<id>`, `interactions`): seq 없이 메시지를 그대로 나눠 준다. */
interface PlainTopicEntry {
  topic: string;
  handlers: Set<(message: WsServerMessage) => void>;
  onError: ((e: ErrorInfo) => void) | undefined;
}

const MAX_TRACKED_REQUESTS = 200;

/** 로그 수집 알림 토픽 이름(서버와 정확히 일치). */
const LOGS_TOPIC = "logs";
/** 공유 메모리 변경 알림 토픽 이름(서버와 정확히 일치). */
const MEMORY_TOPIC = "memory.changed";

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null;
}

function toWsBase(baseUrl: string): string {
  return baseUrl.replace(/\/+$/, "").replace(/^http/i, "ws");
}

/**
 * WebSocket 클라이언트를 만든다(단일 소켓 `/ws`, 재접속·since_seq 재생·중복 제거).
 * @param options 서버 주소·토큰·구현 주입
 */
export function createWsClient(options: WsClientOptions): WsClient {
  const backoff = {
    initialMs: options.backoff?.initialMs ?? 500,
    maxMs: options.backoff?.maxMs ?? 10_000,
    factor: options.backoff?.factor ?? 2,
    jitter: options.backoff?.jitter ?? 0.2,
  };
  const timers: TimerApi = options.timers ?? {
    setTimeout: (fn, ms) => globalThis.setTimeout(fn, ms),
    clearTimeout: (h) => globalThis.clearTimeout(h as ReturnType<typeof setTimeout>),
  };
  const random = options.random ?? Math.random;
  let idCounter = 0;
  const nextId = options.nextId ?? (() => `c${++idCounter}`);
  const stableMs = options.stableMs ?? 10_000;
  const noReconnect = new Set(options.noReconnectCloseCodes ?? WS_AUTH_CLOSE_CODES);
  const createSocket: WebSocketFactory =
    options.webSocket ?? ((url) => new globalThis.WebSocket(url) as unknown as WebSocketLike);

  let status: ConnectionStatus = "idle";
  let socket: WebSocketLike | undefined;
  let attempt = 0;
  let retryTimer: unknown;
  let stableTimer: unknown;
  const statusListeners = new Set<(s: ConnectionStatus) => void>();
  const messageListeners = new Set<(m: WsServerMessage) => void>();
  const topics = new Map<string, TopicEntry>();
  const plainTopics = new Map<string, PlainTopicEntry>();
  const requestOwners = new Map<string, (e: ErrorInfo) => void>();

  /** 핸들러 예외를 격리해 onError로 보고한다(onError가 던져도 무시). */
  function guard(fn: () => void): void {
    try {
      fn();
    } catch (cause) {
      try {
        options.onError?.({
          code: "handler_error",
          message: cause instanceof Error ? cause.message : String(cause),
        });
      } catch {
        /* 무시 */
      }
    }
  }

  function setStatus(next: ConnectionStatus): void {
    if (status === next) return;
    status = next;
    for (const l of [...statusListeners]) guard(() => l(next));
  }

  function clearStable(): void {
    if (stableTimer !== undefined) timers.clearTimeout(stableTimer);
    stableTimer = undefined;
  }

  function isOpen(): boolean {
    return socket !== undefined && socket.readyState === WS_OPEN;
  }

  function track(id: string, owner: ((e: ErrorInfo) => void) | undefined): void {
    if (owner === undefined) return;
    requestOwners.set(id, owner);
    if (requestOwners.size > MAX_TRACKED_REQUESTS) {
      const oldest = requestOwners.keys().next();
      if (!oldest.done) requestOwners.delete(oldest.value);
    }
  }

  function send(message: WsClientMessage): void {
    socket?.send(JSON.stringify(message));
  }

  function sendSubscribe(entry: TopicEntry | PlainTopicEntry): void {
    const id = nextId();
    track(id, entry.onError);
    const payload: { topic: string; since_seq?: number } = { topic: entry.topic };
    if ("lastSeq" in entry && entry.lastSeq > 0) payload.since_seq = entry.lastSeq;
    send({ id, type: "subscribe", payload });
  }

  function onSocketOpen(): void {
    clearStable();
    stableTimer = timers.setTimeout(() => {
      stableTimer = undefined;
      attempt = 0;
    }, stableMs);
    setStatus("open");
    for (const t of topics.values()) sendSubscribe(t);
    for (const t of plainTopics.values()) sendSubscribe(t);
  }

  function scheduleReconnect(): void {
    clearStable();
    const delay =
      Math.min(backoff.maxMs, backoff.initialMs * backoff.factor ** attempt) *
      (1 - backoff.jitter * random());
    attempt += 1;
    setStatus("reconnecting");
    retryTimer = timers.setTimeout(() => {
      retryTimer = undefined;
      openSocket();
    }, delay);
  }

  function openSocket(): void {
    const token = resolveToken(options.token);
    const base = `${toWsBase(options.baseUrl)}/ws`;
    const url = token !== undefined && token !== "" ? `${base}?token=${encodeURIComponent(token)}` : base;
    let ws: WebSocketLike;
    try {
      ws = createSocket(url);
    } catch {
      scheduleReconnect();
      return;
    }
    socket = ws;
    if (status !== "reconnecting") setStatus("connecting");
    ws.onopen = () => {
      if (socket === ws) onSocketOpen();
    };
    ws.onmessage = (ev: { data?: unknown }) => {
      if (socket !== ws) return;
      attempt = 0;
      handleRaw(ev.data);
    };
    ws.onerror = () => {
      /* 실패는 onclose에서 재접속으로 처리한다. */
    };
    ws.onclose = (ev: { code?: unknown }) => {
      if (socket !== ws) return;
      socket = undefined;
      clearStable();
      if (typeof ev?.code === "number" && noReconnect.has(ev.code)) {
        setStatus("closed");
        return;
      }
      scheduleReconnect();
    };
  }

  function handleRaw(data: unknown): void {
    if (typeof data !== "string") return;
    let msg: unknown;
    try {
      msg = JSON.parse(data);
    } catch {
      return;
    }
    if (!isRecord(msg) || typeof msg["type"] !== "string" || !isRecord(msg["payload"])) return;
    const message = msg as unknown as WsServerMessage;
    for (const l of [...messageListeners]) guard(() => l(message));
    switch (message.type) {
      case "run.event":
        return handleRunEvent(message.payload);
      case "conversation.updated":
        return dispatchPlain(`conversation:${message.payload.conversation?.id}`, message);
      case "interaction.updated":
        return dispatchPlain("interactions", message);
      case "logs.ingested":
        return dispatchPlain(LOGS_TOPIC, message);
      case "memory.changed":
        return dispatchPlain(MEMORY_TOPIC, message);
      case "error":
        return handleError(message.payload, message.id ?? undefined);
      default:
        return;
    }
  }

  function dispatchPlain(topic: string, message: WsServerMessage): void {
    const entry = plainTopics.get(topic);
    if (entry === undefined) return;
    for (const h of [...entry.handlers]) guard(() => h(message));
  }

  function handleRunEvent(event: RunEvent): void {
    if (typeof event.run_id !== "string" || typeof event.seq !== "number") return;
    const entry = topics.get(`run:${event.run_id}`);
    if (entry === undefined || event.seq <= entry.lastSeq) return;
    entry.lastSeq = event.seq;
    for (const h of [...entry.handlers]) guard(() => h(event));
  }

  function handleError(error: ErrorInfo, requestId: string | undefined): void {
    const owner = requestId === undefined ? undefined : requestOwners.get(requestId);
    if (requestId !== undefined) requestOwners.delete(requestId);
    if (owner !== undefined) guard(() => owner(error));
    else options.onError?.(error, requestId);
  }

  function connect(): void {
    if (status === "connecting" || status === "open" || status === "reconnecting") return;
    attempt = 0;
    openSocket();
  }

  function close(): void {
    if (retryTimer !== undefined) timers.clearTimeout(retryTimer);
    retryTimer = undefined;
    clearStable();
    const ws = socket;
    socket = undefined;
    topics.clear();
    plainTopics.clear();
    requestOwners.clear();
    setStatus("closed");
    ws?.close();
  }

  function subscribe(
    topic: string,
    handler: (event: RunEvent) => void,
    opts: SubscribeOptions = {},
  ): Subscription {
    let entry = topics.get(topic);
    const isNew = entry === undefined;
    if (entry === undefined) {
      entry = { topic, lastSeq: opts.sinceSeq ?? 0, handlers: new Set(), onError: opts.onError };
      topics.set(topic, entry);
    }
    entry.handlers.add(handler);
    if (isNew && isOpen()) sendSubscribe(entry);
    connect();
    const created = entry;
    return {
      topic,
      unsubscribe() {
        if (!created.handlers.delete(handler) || created.handlers.size > 0) return;
        if (topics.get(topic) === created) topics.delete(topic);
        if (isOpen()) send({ id: nextId(), type: "unsubscribe", payload: { topic } });
      },
    };
  }

  function subscribePlain(
    topic: string,
    handler: (message: WsServerMessage) => void,
    onError: ((e: ErrorInfo) => void) | undefined,
  ): Subscription {
    let entry = plainTopics.get(topic);
    const isNew = entry === undefined;
    if (entry === undefined) {
      entry = { topic, handlers: new Set(), onError };
      plainTopics.set(topic, entry);
    }
    entry.handlers.add(handler);
    if (isNew && isOpen()) sendSubscribe(entry);
    connect();
    const created = entry;
    return {
      topic,
      unsubscribe() {
        if (!created.handlers.delete(handler) || created.handlers.size > 0) return;
        if (plainTopics.get(topic) === created) plainTopics.delete(topic);
        if (isOpen()) send({ id: nextId(), type: "unsubscribe", payload: { topic } });
      },
    };
  }

  return {
    get status() {
      return status;
    },
    connect,
    close,
    onStatus(listener) {
      statusListeners.add(listener);
      return () => statusListeners.delete(listener);
    },
    subscribe,
    subscribeConversation: (id, handler, opts) =>
      subscribePlain(
        `conversation:${id}`,
        (m) => {
          if (m.type === "conversation.updated") handler(m.payload.conversation);
        },
        opts?.onError,
      ),
    subscribeInteractions: (handler, opts) =>
      subscribePlain(
        "interactions",
        (m) => {
          if (m.type === "interaction.updated") handler(m.payload.interaction);
        },
        opts?.onError,
      ),
    subscribeLogs: (handler, opts) =>
      subscribePlain(
        LOGS_TOPIC,
        (m) => {
          if (m.type === "logs.ingested") handler(m.payload);
        },
        opts?.onError,
      ),
    subscribeMemory: (handler, opts) =>
      subscribePlain(
        MEMORY_TOPIC,
        (m) => {
          if (m.type === "memory.changed") handler(m.payload);
        },
        opts?.onError,
      ),
    subscribeRun: (runId, handler, opts) => subscribe(`run:${runId}`, handler, opts),
    onMessage(listener) {
      messageListeners.add(listener);
      return () => messageListeners.delete(listener);
    },
  };
}
