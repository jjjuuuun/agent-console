import { ERROR_CODES } from "@agent-console/contracts";
import type { Graph, RunEvent, WsServerMessage } from "@agent-console/contracts";
import { describe, expect, it, vi } from "vitest";
import {
  ApiError,
  createClient,
  createRestClient,
  createWsClient,
  PACKAGE_NAME,
  type FetchLike,
  type TimerApi,
  type WebSocketLike,
} from "./index";

// ---- 가짜 fetch ----
interface Call {
  url: string;
  init: RequestInit;
}
function fakeFetch(respond: (call: Call) => { status?: number; body?: unknown; text?: string }) {
  const calls: Call[] = [];
  const fn: FetchLike = (url, init = {}) => {
    const call = { url, init };
    calls.push(call);
    const r = respond(call);
    const text = r.text ?? (r.body === undefined ? "" : JSON.stringify(r.body));
    return Promise.resolve(new Response(text === "" ? null : text, { status: r.status ?? 200 }));
  };
  return { fn, calls };
}
const headersOf = (c: Call) => c.init.headers as Record<string, string>;
const graph = { id: "g1", name: "G" } as unknown as Graph;

describe("REST", () => {
  it("스모크: 패키지를 단독으로 import할 수 있다", () => {
    expect(PACKAGE_NAME).toBe("@agent-console/api-client");
  });

  it("GET은 경로·Accept를 맞추고 JSON을 돌려준다, 토큰은 X-Console-Token", async () => {
    const { fn, calls } = fakeFetch(() => ({ body: [{ id: "g1" }] }));
    const rest = createRestClient({ baseUrl: "http://h:1/", token: "tok", fetch: fn });
    const out = await rest.listGraphs();
    expect(out).toEqual([{ id: "g1" }]);
    expect(calls[0]?.url).toBe("http://h:1/api/v1/graphs");
    expect(headersOf(calls[0]!)["X-Console-Token"]).toBe("tok");
    expect(calls[0]?.init.method).toBe("GET");
  });

  it("토큰 함수는 호출 때마다 읽고, 없으면 헤더를 보내지 않는다", async () => {
    let t: string | undefined = undefined;
    const { fn, calls } = fakeFetch(() => ({ body: [] }));
    const rest = createRestClient({ baseUrl: "http://h", token: () => t, fetch: fn });
    await rest.listAgents();
    t = "later";
    await rest.listAgents();
    expect(headersOf(calls[0]!)["X-Console-Token"]).toBeUndefined();
    expect(headersOf(calls[1]!)["X-Console-Token"]).toBe("later");
  });

  it("updateGraph는 If-Match와 본문을 보낸다", async () => {
    const { fn, calls } = fakeFetch(() => ({ body: { graph, version_hash: "h2" } }));
    const rest = createRestClient({ baseUrl: "http://h", fetch: fn });
    const out = await rest.updateGraph("g 1", graph, "h1");
    expect(out.version_hash).toBe("h2");
    expect(calls[0]?.url).toBe("http://h/api/v1/graphs/g%201");
    expect(calls[0]?.init.method).toBe("PUT");
    expect(headersOf(calls[0]!)["If-Match"]).toBe("h1");
    expect(JSON.parse(calls[0]?.init.body as string)).toEqual(graph);
  });

  it("412는 ApiError로 던지고 versionConflict를 노출한다", async () => {
    const details = { current_version_hash: "h9", saved_at: 5, node_count: 2, edge_count: 1 };
    const { fn } = fakeFetch(() => ({
      status: 412,
      body: { error: { code: "version_conflict", message: "다른 곳에서 저장됨", details } },
    }));
    const rest = createRestClient({ baseUrl: "http://h", fetch: fn });
    const err = await rest.updateGraph("g1", graph, "old").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    const e = err as ApiError;
    expect(e.status).toBe(412);
    expect(e.code).toBe(ERROR_CODES.VERSION_CONFLICT);
    expect(e.message).toBe("다른 곳에서 저장됨");
    expect(e.versionConflict).toEqual(details);
  });

  it("428·404 등 다른 오류는 versionConflict가 없다", async () => {
    const { fn } = fakeFetch(() => ({
      status: 428,
      body: { error: { code: "version_required", message: "If-Match 필요" } },
    }));
    const rest = createRestClient({ baseUrl: "http://h", fetch: fn });
    const e = (await rest.deleteGraph("g1").catch((x: unknown) => x)) as ApiError;
    expect(e.code).toBe("version_required");
    expect(e.status).toBe(428);
    expect(e.versionConflict).toBeUndefined();
    expect(e.details).toEqual({});
  });

  it("모르는 code는 그대로, 본문이 JSON이 아니면 상태로 code를 추정한다", async () => {
    const a = createRestClient({
      baseUrl: "http://h",
      fetch: fakeFetch(() => ({
        status: 400,
        body: { error: { code: "plugin_x", message: "m", details: { k: 1 } } },
      })).fn,
    });
    const ea = (await a.getSettings().catch((x: unknown) => x)) as ApiError;
    expect([ea.code, ea.details]).toEqual(["plugin_x", { k: 1 }]);

    const b = createRestClient({
      baseUrl: "http://h",
      fetch: fakeFetch(() => ({ status: 404, text: "Not here" })).fn,
    });
    const eb = (await b.getRun("r").catch((x: unknown) => x)) as ApiError;
    expect([eb.code, eb.status, eb.message]).toEqual(["not_found", 404, "Not here"]);

    const c = createRestClient({
      baseUrl: "http://h",
      fetch: fakeFetch(() => ({ status: 502, text: "" })).fn,
    });
    const ec = (await c.getRun("r").catch((x: unknown) => x)) as ApiError;
    expect(ec.code).toBe("http_502");
  });

  it("네트워크 실패는 network_error(status 0)", async () => {
    const rest = createRestClient({
      baseUrl: "http://h",
      fetch: () => Promise.reject(new TypeError("fetch failed")),
    });
    const e = (await rest.getBootstrap().catch((x: unknown) => x)) as ApiError;
    expect([e.status, e.code, e.message]).toEqual([0, "network_error", "fetch failed"]);
  });

  it("나머지 엔드포인트의 메서드·경로·본문", async () => {
    const { fn, calls } = fakeFetch(() => ({ status: 202, body: {} }));
    const rest = createRestClient({ baseUrl: "http://h", fetch: fn });
    await rest.getBootstrap();
    await rest.listNodeTypes();
    await rest.resolvePorts("agent", { a: 1 });
    await rest.listEdgeTypes();
    await rest.listBackends();
    await rest.listBackendModels("fake");
    await rest.createGraph(graph);
    await rest.validateGraph("g1");
    await rest.validateGraph("g1", graph);
    await rest.listGraphVersions("g1");
    await rest.getGraphVersion("g1", "abc");
    await rest.createRun({ graph_id: "g1", input: {}, origin: "web" });
    await rest.listRuns({ graph_id: "g1" });
    await rest.listRuns();
    await rest.cancelRun("r1");
    await rest.putSettings({} as never);
    await rest.createAgent({ id: "a" } as never);
    await rest.updateAgent("a", { id: "a" } as never);
    await rest.deleteAgent("a");
    const seen = calls.map((c) => `${c.init.method} ${c.url.replace("http://h/api/v1", "")}`);
    expect(seen).toEqual([
      "GET /bootstrap",
      "GET /node-types",
      "POST /node-types/agent/ports",
      "GET /edge-types",
      "GET /backends",
      "GET /backends/fake/models",
      "POST /graphs",
      "POST /graphs/g1/validate",
      "POST /graphs/g1/validate",
      "GET /graphs/g1/versions",
      "GET /graphs/g1/versions/abc",
      "POST /runs",
      "GET /runs?graph_id=g1",
      "GET /runs",
      "POST /runs/r1/cancel",
      "PUT /settings",
      "POST /agents",
      "PUT /agents/a",
      "DELETE /agents/a",
    ]);
    expect(JSON.parse(calls[2]?.init.body as string)).toEqual({ config: { a: 1 } });
    expect(calls[7]?.init.body).toBeUndefined();
    expect(JSON.parse(calls[8]?.init.body as string)).toEqual(graph);
  });
});

// ---- 가짜 WebSocket / 타이머 ----
class FakeSocket implements WebSocketLike {
  readyState = 0;
  sent: Array<Record<string, unknown>> = [];
  onopen: ((ev: unknown) => void) | null = null;
  onmessage: ((ev: { data: unknown }) => void) | null = null;
  onclose: ((ev: unknown) => void) | null = null;
  onerror: ((ev: unknown) => void) | null = null;
  constructor(readonly url: string) {}
  send(data: string): void {
    this.sent.push(JSON.parse(data) as Record<string, unknown>);
  }
  close(): void {
    this.readyState = 3;
  }
  // 서버 쪽 조작
  open(): void {
    this.readyState = 1;
    this.onopen?.({});
  }
  push(msg: unknown): void {
    this.onmessage?.({ data: JSON.stringify(msg) });
  }
  drop(): void {
    this.readyState = 3;
    this.onclose?.({});
  }
}

function setup(extra: { token?: string | (() => string | undefined) } = {}) {
  const sockets: FakeSocket[] = [];
  const pending: Array<{ fn: () => void; ms: number; cancelled: boolean }> = [];
  const timers: TimerApi = {
    setTimeout(fn, ms) {
      const t = { fn, ms, cancelled: false };
      pending.push(t);
      return t;
    },
    clearTimeout(h) {
      (h as { cancelled: boolean }).cancelled = true;
    },
  };
  const onError = vi.fn();
  const ws = createWsClient({
    baseUrl: "http://127.0.0.1:8765/",
    ...extra,
    webSocket: (url) => {
      const s = new FakeSocket(url);
      sockets.push(s);
      return s;
    },
    backoff: { initialMs: 100, maxMs: 350, factor: 2, jitter: 0 },
    timers,
    onError,
  });
  const fire = () => {
    const t = pending.find((x) => !x.cancelled);
    if (t === undefined) throw new Error("대기 중 타이머 없음");
    t.cancelled = true;
    t.fn();
    return t.ms;
  };
  const last = () => sockets[sockets.length - 1]!;
  return { ws, sockets, last, fire, onError };
}

const runEvent = (seq: number, run_id = "r1", type = "node.started"): WsServerMessage =>
  ({
    type: "run.event",
    payload: {
      schema_version: 1,
      event_id: `e${seq}`,
      run_id,
      seq,
      ts: 1,
      type,
      node_path: [],
      payload: {},
    },
  }) as unknown as WsServerMessage;

describe("WS run 구독", () => {
  it("주소는 ws:///ws?token=, 열리면 subscribe를 보낸다", () => {
    const { ws, last } = setup({ token: "a b" });
    ws.subscribeRun("r1", () => {});
    expect(last().url).toBe("ws://127.0.0.1:8765/ws?token=a%20b");
    expect(ws.status).toBe("connecting");
    last().open();
    expect(ws.status).toBe("open");
    expect(last().sent).toMatchObject([{ type: "subscribe", payload: { topic: "run:r1" } }]);
    expect(last().sent[0]?.["payload"]).not.toHaveProperty("since_seq");
    expect(typeof last().sent[0]?.["id"]).toBe("string");
  });

  it("같은 seq 재전송·역순은 버리고 순서대로 한 번씩 전달한다", () => {
    const { ws, last } = setup();
    const got: number[] = [];
    ws.subscribeRun("r1", (e) => got.push(e.seq));
    last().open();
    for (const s of [1, 2, 2, 3, 1, 4]) last().push(runEvent(s));
    last().push(runEvent(1, "other"));
    expect(got).toEqual([1, 2, 3, 4]);
  });

  it("끊기면 백오프로 재접속하고 마지막 seq를 since_seq로 보낸다, 재생분 중복은 버린다", () => {
    const { ws, sockets, last, fire } = setup();
    const got: number[] = [];
    ws.subscribeRun("r1", (e) => got.push(e.seq));
    last().open();
    last().push(runEvent(1));
    last().push(runEvent(2));
    last().drop();
    expect(ws.status).toBe("reconnecting");
    expect(fire()).toBe(100);
    expect(sockets).toHaveLength(2);
    last().drop(); // 두 번째 시도 실패
    expect(fire()).toBe(200);
    last().drop();
    expect(fire()).toBe(350); // maxMs 상한
    last().open();
    expect(ws.status).toBe("open");
    expect(last().sent).toMatchObject([
      { type: "subscribe", payload: { topic: "run:r1", since_seq: 2 } },
    ]);
    // 서버가 경계를 넘겨 재생(2부터)해도 중복 없이 이어받는다
    last().push(runEvent(2));
    last().push(runEvent(3));
    last().push(runEvent(4));
    expect(got).toEqual([1, 2, 3, 4]);
    // 메시지를 받은 연결이었으므로 백오프가 초기화된다
    last().drop();
    expect(fire()).toBe(100);
  });

  it("sinceSeq 옵션 이하는 버리고 재접속 때도 그 값부터 요청한다", () => {
    const { ws, last, fire } = setup();
    const got: number[] = [];
    ws.subscribeRun("r1", (e) => got.push(e.seq), { sinceSeq: 5 });
    last().open();
    expect(last().sent[0]?.["payload"]).toMatchObject({ since_seq: 5 });
    last().push(runEvent(5));
    last().push(runEvent(6));
    last().drop();
    fire();
    last().open();
    expect(last().sent[0]?.["payload"]).toMatchObject({ since_seq: 6 });
    expect(got).toEqual([6]);
  });

  it("재접속 때마다 토큰 함수를 다시 읽는다", () => {
    let n = 0;
    const { ws, last, fire } = setup({ token: () => `t${++n}` });
    ws.subscribeRun("r1", () => {});
    expect(last().url).toContain("token=t1");
    last().drop();
    fire();
    expect(last().url).toContain("token=t2");
  });

  it("unsubscribe는 마지막 구독자가 빠질 때 unsubscribe를 보내고 이후 이벤트·재접속에서 제외", () => {
    const { ws, last, fire } = setup();
    const a: number[] = [];
    const b: number[] = [];
    const sa = ws.subscribeRun("r1", (e) => a.push(e.seq));
    const sb = ws.subscribeRun("r1", (e) => b.push(e.seq));
    last().open();
    expect(last().sent).toHaveLength(1); // 소켓 구독은 하나
    last().push(runEvent(1));
    sa.unsubscribe();
    expect(last().sent).toHaveLength(1);
    last().push(runEvent(2));
    sb.unsubscribe();
    expect(last().sent[1]).toMatchObject({ type: "unsubscribe", payload: { topic: "run:r1" } });
    last().push(runEvent(3));
    expect([a, b]).toEqual([[1], [1, 2]]);
    last().drop();
    fire();
    last().open();
    expect(last().sent).toEqual([]);
  });

  it("모르는 type 이벤트도 일반형으로 전달하고, error는 요청 id로 귀속시킨다", () => {
    const { ws, last, onError } = setup();
    const got: RunEvent[] = [];
    const subErr = vi.fn();
    ws.subscribeRun("r1", (e) => got.push(e));
    last().open();
    last().push(runEvent(1, "r1", "plugin.custom"));
    expect(got[0]?.type).toBe("plugin.custom");

    ws.subscribe("graph:g1", () => {}, { onError: subErr });
    const id = last().sent[last().sent.length - 1]?.["id"];
    last().push({ type: "error", id, payload: { code: "not_found", message: "x" } });
    last().push({ type: "error", payload: { code: "internal", message: "y" } });
    expect(subErr).toHaveBeenCalledWith({ code: "not_found", message: "x" });
    expect(onError).toHaveBeenCalledTimes(1);
    expect(onError).toHaveBeenCalledWith({ code: "internal", message: "y" }, undefined);
  });

  it("onMessage는 원본 메시지를 모두 받는다. 깨진 JSON은 무시", () => {
    const { ws, last } = setup();
    const raw: string[] = [];
    ws.onMessage((m) => raw.push(m.type));
    ws.subscribeRun("r1", () => {});
    last().open();
    last().onmessage?.({ data: "{not json" });
    last().push(runEvent(1));
    last().push(runEvent(1));
    expect(raw).toEqual(["run.event", "run.event"]);
  });

  it("close()는 재접속을 멈춘다. 이후 connect()로 다시 시작 가능", () => {
    const { ws, sockets, last, fire } = setup();
    ws.subscribeRun("r1", () => {});
    last().drop();
    ws.close();
    expect(ws.status).toBe("closed");
    expect(() => fire()).toThrow();
    expect(sockets).toHaveLength(1);
    ws.connect();
    expect(sockets).toHaveLength(2);
  });

  it("열려 있는 동안 늦게 구독하면 바로 subscribe를 보낸다", () => {
    const { ws, last } = setup();
    ws.connect();
    last().open();
    ws.subscribeRun("r2", () => {});
    expect(last().sent).toMatchObject([{ type: "subscribe", payload: { topic: "run:r2" } }]);
  });
});

describe("WS 견고성", () => {
  it("열기 전에 구독한 onError도 귀속되고 재접속 후에도 유지된다", () => {
    const { ws, last, fire, onError } = setup();
    const subErr = vi.fn();
    ws.subscribeRun("r1", () => {}, { onError: subErr });
    last().open();
    const id1 = last().sent[0]?.["id"];
    last().push({ type: "error", id: id1, payload: { code: "not_found", message: "a" } });
    expect(subErr).toHaveBeenCalledTimes(1);
    last().drop();
    fire();
    last().open();
    const id2 = last().sent[0]?.["id"];
    expect(id2).not.toBe(id1);
    last().push({ type: "error", id: id2, payload: { code: "not_found", message: "b" } });
    expect(subErr).toHaveBeenCalledTimes(2);
    expect(onError).not.toHaveBeenCalled();
  });

  it("두 번째 구독의 onError·sinceSeq는 무시된다", () => {
    const { ws, last } = setup();
    const first = vi.fn();
    const second = vi.fn();
    ws.subscribeRun("r1", () => {}, { onError: first });
    ws.subscribeRun("r1", () => {}, { onError: second, sinceSeq: 9 });
    last().open();
    expect(last().sent).toHaveLength(1);
    expect(last().sent[0]?.["payload"]).not.toHaveProperty("since_seq");
    last().push({
      type: "error",
      id: last().sent[0]?.["id"],
      payload: { code: "x", message: "m" },
    });
    expect([first.mock.calls.length, second.mock.calls.length]).toEqual([1, 0]);
  });

  it("열자마자 닫히면 백오프가 계속 늘어난다, 메시지를 받거나 오래 유지하면 초기화", () => {
    const { ws, last, fire } = setup();
    ws.subscribeRun("r1", () => {});
    const delays: number[] = [];
    for (let i = 0; i < 3; i++) {
      last().open();
      last().drop();
      delays.push(fire());
    }
    expect(delays).toEqual([100, 200, 350]);
    last().open();
    expect(fire()).toBe(10_000); // 안정 타이머 만료 → 초기화
    last().drop();
    expect(fire()).toBe(100);
  });

  it("noReconnectCloseCodes에 있는 코드로 닫히면 재접속하지 않는다", () => {
    const sockets: FakeSocket[] = [];
    const ws = createWsClient({
      baseUrl: "http://h",
      noReconnectCloseCodes: [4401],
      webSocket: (u) => {
        const s = new FakeSocket(u);
        sockets.push(s);
        return s;
      },
    });
    ws.connect();
    sockets[0]?.open();
    sockets[0]?.onclose?.({ code: 4401 });
    expect(ws.status).toBe("closed");
    expect(sockets).toHaveLength(1);
  });

  it("핸들러 예외는 격리되어 onError(handler_error)로 보고되고 다른 핸들러는 계속 받는다", () => {
    const { ws, last, onError } = setup();
    const got: number[] = [];
    ws.subscribeRun("r1", () => {
      throw new Error("boom");
    });
    ws.subscribeRun("r1", (e) => got.push(e.seq));
    last().open();
    last().push(runEvent(1));
    last().push(runEvent(2));
    expect(got).toEqual([1, 2]);
    expect(onError.mock.calls.map((c) => (c[0] as { message: string }).message)).toEqual([
      "boom",
      "boom",
    ]);
    expect(onError.mock.calls[0]?.[0]).toMatchObject({ code: "handler_error" });
  });
});

describe("createClient", () => {
  it("REST와 WS를 같은 주소·토큰으로 만든다", async () => {
    const { fn, calls } = fakeFetch(() => ({ body: [] }));
    const urls: string[] = [];
    const { rest, ws } = createClient({
      baseUrl: "https://h:9",
      token: "T",
      fetch: fn,
      webSocket: (u) => {
        urls.push(u);
        return new FakeSocket(u);
      },
    });
    await rest.listGraphs();
    ws.connect();
    ws.close();
    expect(calls[0]?.url).toBe("https://h:9/api/v1/graphs");
    expect(urls).toEqual(["wss://h:9/ws?token=T"]);
  });
});
