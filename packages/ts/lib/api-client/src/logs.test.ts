import { describe, expect, it } from "vitest";
import { createRestClient, createWsClient, logQuery, type FetchLike, type WebSocketLike } from "./index";
import { createLogsClient } from "./clients/logs";
import { createRestIo } from "./transport";

interface Call {
  method: string;
  path: string;
  body: unknown;
}
function server(reply: (c: Call) => { status?: number; body?: unknown; headers?: Record<string, string> } = () => ({ body: [] })) {
  const calls: Call[] = [];
  const fetch: FetchLike = (url, init = {}) => {
    const raw = init.body;
    const call: Call = { method: init.method ?? "GET", path: url.replace("http://h/api/v1", ""), body: typeof raw === "string" ? JSON.parse(raw) : undefined };
    calls.push(call);
    const r = reply(call);
    return Promise.resolve(new Response(r.body === undefined ? null : typeof r.body === "string" ? r.body : JSON.stringify(r.body), { status: r.status ?? 200, headers: r.headers }));
  };
  return { calls, rest: createRestClient({ baseUrl: "http://h", token: "T", fetch }), fetch };
}

describe("logQuery", () => {
  it("반복 키 = 다중 값, 빈 값·undefined·null은 보내지 않고 값은 인코딩한다", () => {
    expect(logQuery({ a: ["x", "y z"], b: "1", c: "", d: undefined, e: null, n: 3, ok: false })).toBe("?a=x&a=y%20z&b=1&n=3&ok=false");
    expect(logQuery(undefined)).toBe("");
    expect(logQuery({})).toBe("");
  });
});

describe("로그 REST", () => {
  it("메서드·경로·본문 (필터 이름은 그대로 전달, 모르는 이름도 막지 않음)", async () => {
    const { rest, calls } = server();
    await rest.listLogSources();
    await rest.listLogClassifiers();
    await rest.scanLogs();
    await rest.scanLogs(["a", "b"]);
    await rest.listLogEvents({ q: "x", category: ["c1", "c2"], limit: 100, order: "desc" });
    await rest.listLogSessions({ order: "desc", zzz: "서버가 판단" });
    await rest.aggregateLogs({ group_by: ["g"], metric: "m", filter: {}, tz: "Asia/Seoul" });
    await rest.getLogHandoffs({ since: "2026-01-01T00:00:00Z" });
    await rest.getLogTaxonomy();
    await rest.listLogDashboardTemplates();
    await rest.getLogSchema();
    await rest.listRunLogs("r/1", { q: "a" });
    expect(calls.map((c) => `${c.method} ${c.path}`)).toEqual([
      "GET /logs/sources",
      "GET /logs/classifiers",
      "POST /logs/scan",
      "POST /logs/scan",
      "GET /logs/events?q=x&category=c1&category=c2&limit=100&order=desc",
      "GET /logs/sessions?order=desc&zzz=%EC%84%9C%EB%B2%84%EA%B0%80%20%ED%8C%90%EB%8B%A8",
      "POST /logs/aggregate",
      "GET /logs/handoffs?since=2026-01-01T00%3A00%3A00Z",
      "GET /logs/taxonomy",
      "GET /logs/dashboard-templates",
      "GET /logs/schema",
      "GET /runs/r%2F1/logs?q=a",
    ]);
    expect(calls[3]!.body).toEqual({ source_ids: ["a", "b"] });
    expect(calls[6]!.body).toEqual({ group_by: ["g"], metric: "m", filter: {}, tz: "Asia/Seoul" });
  });

  it("세션·이벤트 경로는 id를 인코딩한다", async () => {
    const { rest, calls } = server(() => ({ body: {} }));
    await rest.getLogEvent("a/b c");
    await rest.getLogTimeline("s 1", { lane: "x" });
    await rest.getLogSessionTrace("s/1");
    expect(calls.map((c) => c.path)).toEqual(["/logs/events/a%2Fb%20c", "/logs/sessions/s%201/timeline?lane=x", "/logs/sessions/s%2F1/trace"]);
  });

  it("보관본: 필터 + format + tz를 쿼리로, 파일 이름은 Content-Disposition에서", async () => {
    const { rest, calls } = server(() => ({ body: "<html></html>", headers: { "Content-Type": "text/html", "Content-Disposition": 'attachment; filename="logs-1.html"' } }));
    const r = await rest.downloadLogArchive({ filter: { session: "s1" }, format: "html", tz: "Asia/Seoul" });
    expect(calls[0]!.path).toBe("/logs/archive?session=s1&format=html&tz=Asia%2FSeoul");
    expect(r.filename).toBe("logs-1.html");
    expect(r.contentType).toContain("text/html");
  });

  it("기능 하나만 전송으로 단독 사용한다", async () => {
    const { calls, fetch } = server();
    await createLogsClient(createRestIo({ baseUrl: "http://h", fetch })).listLogSources();
    expect(calls[0]!.path).toBe("/logs/sources");
  });
});

class FakeSocket implements WebSocketLike {
  readyState = 0;
  sent: Array<Record<string, unknown>> = [];
  onopen: ((ev: unknown) => void) | null = null;
  onmessage: ((ev: { data: unknown }) => void) | null = null;
  onclose: ((ev: unknown) => void) | null = null;
  onerror: ((ev: unknown) => void) | null = null;
  send(data: string): void {
    this.sent.push(JSON.parse(data) as Record<string, unknown>);
  }
  close(): void {
    this.readyState = 3;
  }
  open(): void {
    this.readyState = 1;
    this.onopen?.({});
  }
  push(msg: unknown): void {
    this.onmessage?.({ data: JSON.stringify(msg) });
  }
}

describe("WS logs 토픽", () => {
  it("토픽 이름은 정확히 logs, logs.ingested payload만 전달하고 마지막 구독자가 빠지면 unsubscribe", () => {
    let socket!: FakeSocket;
    const ws = createWsClient({ baseUrl: "http://h", token: "T", webSocket: () => (socket = new FakeSocket()) });
    const got: number[] = [];
    const sub = ws.subscribeLogs((p) => got.push(p.count));
    socket.open();
    expect(socket.sent).toMatchObject([{ type: "subscribe", payload: { topic: "logs" } }]);
    socket.push({ type: "logs.ingested", payload: { source_ids: ["a"], count: 3, max_seq: 9 } });
    socket.push({ type: "interaction.updated", payload: { interaction: { id: "i" } } });
    expect(got).toEqual([3]);
    sub.unsubscribe();
    expect(socket.sent[1]).toMatchObject({ type: "unsubscribe", payload: { topic: "logs" } });
  });
});
