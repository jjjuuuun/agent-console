import { describe, expect, it } from "vitest";
import { ApiError, createRestClient, createWsClient, memoryConflictVersion, memoryScopeText, type FetchLike, type WebSocketLike } from "./index";

interface Call {
  method: string;
  path: string;
  body: unknown;
  headers: Record<string, string>;
  raw: unknown;
}
function server(reply: (c: Call) => { status?: number; body?: unknown; headers?: Record<string, string> } = () => ({ body: {} })) {
  const calls: Call[] = [];
  const fetch: FetchLike = (url, init = {}) => {
    const raw = init.body;
    const call: Call = {
      method: init.method ?? "GET",
      path: url.replace("http://h/api/v1", ""),
      body: typeof raw === "string" ? JSON.parse(raw) : undefined,
      headers: (init.headers ?? {}) as Record<string, string>,
      raw,
    };
    calls.push(call);
    const r = reply(call);
    return Promise.resolve(new Response(r.body === undefined ? null : typeof r.body === "string" ? r.body : JSON.stringify(r.body), { status: r.status ?? 200, headers: r.headers }));
  };
  return { calls, rest: createRestClient({ baseUrl: "http://h", token: "T", fetch }) };
}

const SCOPE = { kind: "k1", id: "a/b c" };

describe("메모리 REST", () => {
  it("메서드·경로·질의 (범위는 <종류>:<id> 반복 키, 값은 인코딩)", async () => {
    const { rest, calls } = server();
    expect(memoryScopeText({ kind: "k", id: "" })).toBe("k:");
    expect(memoryScopeText({ kind: "k" })).toBe("k:");
    await rest.listMemoryScopeKinds();
    await rest.listMemoryScopes();
    await rest.listMemoryScopes("k1");
    await rest.listMemoryTags({ scopes: [SCOPE], includeArchived: true });
    await rest.listMemoryEntries({ scopes: [SCOPE, { kind: "k2" }], q: "찾기", tags: ["t1", "t2"], authorRun: "r1", authorKind: "agent", includeArchived: true, includeDeleted: true, sort: "key", order: "asc", cursor: "c1", limit: 50 });
    await rest.listMemoryEntries();
    await rest.getMemoryEntry("e/1", { includeDeleted: true });
    expect(calls.map((c) => `${c.method} ${c.path}`)).toEqual([
      "GET /memory/scope-kinds",
      "GET /memory/scopes",
      "GET /memory/scopes?kind=k1",
      "GET /memory/tags?scope=k1%3Aa%2Fb%20c&include_archived=true",
      "GET /memory/entries?scope=k1%3Aa%2Fb%20c&scope=k2%3A&q=%EC%B0%BE%EA%B8%B0&tag=t1&tag=t2&author_run=r1&author_kind=agent&include_archived=true&include_deleted=true&sort=key&order=asc&cursor=c1&limit=50",
      "GET /memory/entries",
      "GET /memory/entries/e%2F1?include_deleted=true",
    ]);
  });

  it("쓰기: PUT은 If-Match(버전), 지우기·옮기기·보관·되돌리기 경로", async () => {
    const { rest, calls } = server((c) => (c.method === "DELETE" && c.path.includes("purge") ? { status: 204 } : { body: [] }));
    await rest.createMemoryEntry({ scope: SCOPE, key: "a", content: "x" });
    await rest.updateMemoryEntry("e1", { content: "y" }, 3);
    await rest.deleteMemoryEntry("e1", 4);
    await rest.deleteMemoryEntry("e1");
    await expect(rest.purgeMemoryEntry("e1")).resolves.toBeUndefined();
    await rest.moveMemoryEntry("e1", { to_key: "b" }, 5);
    await rest.archiveMemoryEntry("e1");
    await rest.unarchiveMemoryEntry("e1", 6);
    await rest.restoreMemoryEntry("e1");
    await rest.restoreMemoryEntry("e1", 2);
    await rest.listMemoryVersions("e1");
    await rest.getMemoryVersion("e1", 2);
    expect(calls.map((c) => `${c.method} ${c.path} ${c.headers["If-Match"] ?? "-"}`)).toEqual([
      "POST /memory/entries -",
      "PUT /memory/entries/e1 3",
      "DELETE /memory/entries/e1 4",
      "DELETE /memory/entries/e1 -",
      "DELETE /memory/entries/e1?purge=true -",
      "POST /memory/entries/e1/move 5",
      "POST /memory/entries/e1/archive -",
      "POST /memory/entries/e1/unarchive 6",
      "POST /memory/entries/e1/restore -",
      "POST /memory/entries/e1/restore?version=2 -",
      "GET /memory/entries/e1/versions -",
      "GET /memory/entries/e1/versions/2 -",
    ]);
    expect(calls[1]?.body).toEqual({ content: "y" });
  });

  it("412는 current_version을 읽을 수 있고, 다른 오류는 undefined", async () => {
    const { rest } = server(() => ({ status: 412, body: { error: { code: "version_conflict", message: "달라짐", details: { current_version: 7 } } } }));
    const err = await rest.updateMemoryEntry("e1", { content: "y" }, 3).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(memoryConflictVersion(err)).toBe(7);
    expect(memoryConflictVersion(new ApiError(422, { code: "x", message: "m" }))).toBeUndefined();
    expect(memoryConflictVersion(new Error("x"))).toBeUndefined();
  });

  it("정리·설정 검사·내보내기·가져오기(zip 바이트 그대로, multipart 아님)·색인 비우기", async () => {
    const { rest, calls } = server((c) => (c.path.startsWith("/memory/export") ? { body: "zip", headers: { "Content-Type": "application/zip", "Content-Disposition": 'attachment; filename="memory.zip"' } } : { body: { dry_run: true } }));
    await rest.planMemoryRetention();
    await rest.planMemoryRetention({ rules: [{ id: "r" }], limit: 200 });
    await rest.applyMemoryRetention();
    await rest.checkMemorySettings({ secrets: "reject" });
    const exported = await rest.exportMemory({ scopes: [SCOPE], includeArchived: false });
    expect(exported.filename).toBe("memory.zip");
    const zip = new Uint8Array([80, 75, 3, 4]);
    await rest.importMemory(zip, { policy: "overwrite", dryRun: true });
    await rest.purgeLogIndex({ all: true, dry_run: false });
    expect(calls.map((c) => `${c.method} ${c.path}`)).toEqual([
      "POST /memory/retention/plan",
      "POST /memory/retention/plan",
      "POST /memory/retention/apply",
      "POST /memory/settings/check",
      "GET /memory/export?scope=k1%3Aa%2Fb%20c&include_archived=false",
      "POST /memory/import?policy=overwrite&dry_run=true",
      "POST /logs/index/purge",
    ]);
    expect(calls[5]?.headers["Content-Type"]).toBe("application/zip");
    expect(calls[5]?.raw).toBe(zip);
    expect(calls[1]?.body).toEqual({ rules: [{ id: "r" }], limit: 200 });
    expect(calls[6]?.body).toEqual({ all: true, dry_run: false });
  });
});

class FakeSocket implements WebSocketLike {
  readyState = 0;
  sent: unknown[] = [];
  onopen: ((ev: unknown) => void) | null = null;
  onmessage: ((ev: { data: string }) => void) | null = null;
  onclose: ((ev: unknown) => void) | null = null;
  onerror: ((ev: unknown) => void) | null = null;
  send(data: string): void {
    this.sent.push(JSON.parse(data));
  }
  close(): void {}
  open(): void {
    this.readyState = 1;
    this.onopen?.({});
  }
  push(message: unknown): void {
    this.onmessage?.({ data: JSON.stringify(message) });
  }
}

describe("WS memory.changed", () => {
  it("subscribeMemory는 토픽 memory.changed의 payload를 주고 다른 메시지는 거른다", () => {
    let socket!: FakeSocket;
    const ws = createWsClient({ baseUrl: "http://h", token: "T", webSocket: () => (socket = new FakeSocket()) });
    const got: string[] = [];
    const sub = ws.subscribeMemory((c) => got.push(`${c.entry_id}:${c.op}`));
    socket.open();
    expect(socket.sent).toMatchObject([{ type: "subscribe", payload: { topic: "memory.changed" } }]);
    socket.push({ type: "memory.changed", payload: { scope: { kind: "k" }, key: "a", entry_id: "e1", version: 2, op: "update", author_kind: "user" } });
    socket.push({ type: "logs.ingested", payload: { source_ids: [], count: 1, max_seq: 1 } });
    expect(got).toEqual(["e1:update"]);
    sub.unsubscribe();
    expect(socket.sent[1]).toMatchObject({ type: "unsubscribe", payload: { topic: "memory.changed" } });
  });
});
