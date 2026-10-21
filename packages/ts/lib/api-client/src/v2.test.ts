import { ERROR_CODES } from "@agent-console/contracts";
import type { Interaction, Resource, WsServerMessage } from "@agent-console/contracts";
import { describe, expect, it, vi } from "vitest";
import {
  ApiError,
  createClient,
  createRestClient,
  createWsClient,
  WS_AUTH_CLOSE_CODES,
  WS_CLOSE_FORBIDDEN,
  WS_CLOSE_UNAUTHORIZED,
  type FetchLike,
  type WebSocketLike,
  type WsClientOptions,
} from "./index";

// ---- 가짜 서버(fetch) ----
interface Call {
  method: string;
  path: string;
  headers: Record<string, string>;
  body: unknown;
  rawBody: unknown;
}
interface Reply {
  status?: number;
  body?: unknown;
  text?: string;
  headers?: Record<string, string>;
}
function fakeServer(respond: (call: Call) => Reply = () => ({ body: {} })) {
  const calls: Call[] = [];
  const fn: FetchLike = (url, init = {}) => {
    const raw = init.body;
    const call: Call = {
      method: init.method ?? "GET",
      path: url.replace("http://h/api/v1", ""),
      headers: init.headers as Record<string, string>,
      body: typeof raw === "string" && raw.startsWith("{") ? JSON.parse(raw) : undefined,
      rawBody: raw,
    };
    calls.push(call);
    const r = respond(call);
    const text = r.text ?? (r.body === undefined ? "" : JSON.stringify(r.body));
    return Promise.resolve(
      new Response(text === "" ? null : text, { status: r.status ?? 200, headers: r.headers }),
    );
  };
  return { fn, calls, rest: createRestClient({ baseUrl: "http://h", token: "T", fetch: fn }) };
}

const interaction = (id: string, status: Interaction["status"] = "pending"): Interaction =>
  ({ id, run_id: "r1", kind: "question", status }) as unknown as Interaction;

describe("REST v2: 새 경로", () => {
  it("메서드·경로·쿼리·본문이 §R9.5·§R5.1과 같다", async () => {
    const { rest, calls } = fakeServer((c) =>
      c.path.endsWith("/messages") ? { status: 202, body: { id: "r9" } } : { body: [] },
    );
    await rest.getServerInfo();
    await rest.listDelegationStrategies();
    await rest.listInteractionKinds();
    await rest.listResourceTypes();
    await rest.listAgentUsages("a b");
    await rest.getAgentEffectiveSettings("a");
    await rest.getAgentActivity("a", 5);
    await rest.duplicateGraph("g", { id: "g2", name: "복제" });
    await rest.getNodeEffectiveSettings("g", "n");
    await rest.getNodeBundlePreview("g", "n");
    await rest.listGraphs({ validate: false });
    await rest.getGraphPlan("g 1");
    await rest.planDraftGraph({ graph: { id: "g", name: "g" } as never });
    await rest.previewDraftEffectiveSettings({ graph: { id: "g", name: "g" } as never, node_id: "n" });
    await rest.previewDraftBundle({ graph: { id: "g", name: "g" } as never, node_id: "n" });
    await rest.listRuns({ graph_id: "g", conversation_id: "c", agent_id: "a", status: "waiting", limit: 3 });
    await rest.getRunTrace("r1");
    await rest.listRunEvents("r1", { actor: "pl", type_prefix: "hook." });
    await rest.getHandoffs();
    await rest.getHandoffs({ graph_id: "g" });
    await rest.listConversations({ graph_id: "g", archived: false });
    await rest.createConversation({ graph_id: "g", title: "t" });
    await rest.getConversation("c");
    await rest.updateConversation("c", { graph_id: "g2" });
    await rest.deleteConversation("c");
    await rest.listTurns("c", { before: "r5", limit: 20 });
    await rest.postMessage("c", { text: "안녕" });
    await rest.cancelQueuedMessage("c", "q1");
    await rest.listInteractions({ status: "pending", conversation_id: "c", limit: 10 });
    await rest.listRunInteractions("r1");
    await rest.respondInteraction("r1", "i1", { answer: "예" });
    await rest.getUsage();
    await rest.getUsage(["windows"]);
    await rest.listUsageSources();
    await rest.listPresets();
    await rest.applyPreset("p", { on_conflict: "rename" });
    await rest.listResources({ type: "instruction" });
    await rest.listResourceUsages("res");
    await rest.listImportSources();
    await rest.previewImport({ source: "user-claude" });
    await rest.importResources({ source: "user-claude", items: [{ candidate_id: "c1" }] });
    expect(calls.map((c) => `${c.method} ${c.path}`)).toEqual([
      "GET /server-info",
      "GET /delegation-strategies",
      "GET /interaction-kinds",
      "GET /resource-types",
      "GET /agents/a%20b/usages",
      "GET /agents/a/effective-settings",
      "GET /agents/a/activity?limit=5",
      "POST /graphs/g/duplicate",
      "GET /graphs/g/nodes/n/effective-settings",
      "GET /graphs/g/nodes/n/bundle-preview",
      "GET /graphs?validate=false",
      "GET /graphs/g%201/plan",
      "POST /graphs/plan",
      "POST /graphs/effective-settings",
      "POST /graphs/bundle-preview",
      "GET /runs?graph_id=g&conversation_id=c&agent_id=a&status=waiting&limit=3",
      "GET /runs/r1/trace",
      "GET /runs/r1/events?actor=pl&type_prefix=hook.",
      "GET /runs/handoffs",
      "GET /runs/handoffs?graph_id=g",
      "GET /conversations?graph_id=g&archived=false",
      "POST /conversations",
      "GET /conversations/c",
      "PATCH /conversations/c",
      "DELETE /conversations/c",
      "GET /conversations/c/turns?before=r5&limit=20",
      "POST /conversations/c/messages",
      "DELETE /conversations/c/queue/q1",
      "GET /interactions?status=pending&conversation_id=c&limit=10",
      "GET /runs/r1/interactions",
      "POST /runs/r1/interactions/i1/respond",
      "GET /usage",
      "GET /usage?parts=windows",
      "GET /usage/sources",
      "GET /presets",
      "POST /presets/p/apply",
      "GET /resources?type=instruction",
      "GET /resources/res/usages",
      "GET /resources/import/sources",
      "POST /resources/import/preview",
      "POST /resources/import",
    ]);
    const body = (i: number) => calls[i]?.body;
    expect(body(7)).toEqual({ id: "g2", name: "복제" });
    expect(body(23)).toEqual({ graph_id: "g2" });
    expect(body(13)).toEqual({ graph: { id: "g", name: "g" }, node_id: "n" });
    expect(body(14)).toEqual({ graph: { id: "g", name: "g" }, node_id: "n" });
    expect(body(30)).toEqual({ response: { answer: "예" } });
    expect(body(35)).toEqual({ on_conflict: "rename" });
    expect(calls.every((c) => c.headers["X-Console-Token"] === "T")).toBe(true);
  });

  it("postMessage: Run이면 {run}, 대기열이면 {queued}", async () => {
    let next: unknown = { id: "r1", status: "queued" };
    const { rest } = fakeServer(() => ({ status: 202, body: next }));
    expect(await rest.postMessage("c", { text: "a" })).toEqual({ run: { id: "r1", status: "queued" } });
    next = { queued: true, id: "q1", position: 1 };
    expect(await rest.postMessage("c", { text: "b" })).toEqual({
      queued: { queued: true, id: "q1", position: 1 },
    });
  });

  it("listQueue: 대기열 항목 목록(1 = 다음 차례)", async () => {
    const { rest, calls } = fakeServer(() => ({ body: [{ queued: true, id: "q1", position: 1, text: "다음" }] }));
    expect(await rest.listQueue("c 1")).toEqual([{ queued: true, id: "q1", position: 1, text: "다음" }]);
    expect(calls[0]).toMatchObject({ method: "GET", path: "/conversations/c%201/queue" });
  });

  it("postMessage 거절은 conversation_busy로 구분된다", async () => {
    const { rest } = fakeServer(() => ({
      status: 409,
      body: { error: { code: ERROR_CODES.CONVERSATION_BUSY, message: "실행 중" } },
    }));
    const err = await rest.postMessage("c", { text: "a" }).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).isConversationBusy).toBe(true);
    expect((err as ApiError).isInteractionClosed).toBe(false);
  });

  it("respondInteraction 200은 Interaction을 돌려준다", async () => {
    const { rest } = fakeServer(() => ({ body: interaction("i1", "answered") }));
    expect((await rest.respondInteraction("r1", "i1", {})).status).toBe("answered");
  });

  it("respond 409 interaction_closed는 다른 409와 구분된다", async () => {
    const { rest } = fakeServer(() => ({
      status: 409,
      body: { error: { code: "interaction_closed", message: "이미 닫힘", details: { interaction_id: "i1" } } },
    }));
    const err = (await rest.respondInteraction("r1", "i1", {}).catch((e: unknown) => e)) as ApiError;
    expect(err.status).toBe(409);
    expect(err.code).toBe(ERROR_CODES.INTERACTION_CLOSED);
    expect(err.isInteractionClosed).toBe(true);
    expect(err.details).toEqual({ interaction_id: "i1" });
  });

  it("본문 없는 409는 일반형 already_exists, 422는 validation_failed", async () => {
    const f409 = fakeServer(() => ({ status: 409, text: "충돌" }));
    const e1 = (await f409.rest.createAgent({ id: "a" } as never).catch((e: unknown) => e)) as ApiError;
    expect(e1.code).toBe("already_exists");
    expect(e1.isInteractionClosed).toBe(false);
    const f422 = fakeServer(() => ({
      status: 422,
      body: { error: { code: "validation_failed", message: "응답 형식 오류" } },
    }));
    const e2 = (await f422.rest.respondInteraction("r", "i", {}).catch((e: unknown) => e)) as ApiError;
    expect(e2.status).toBe(422);
    expect(e2.code).toBe(ERROR_CODES.VALIDATION_FAILED);
  });

  it("리소스 CRUD: ETag를 version_hash로 풀고 If-Match를 보낸다", async () => {
    const res = { id: "r", type: "instruction", name: "지침" } as Resource;
    const { rest, calls } = fakeServer(() => ({ body: res, headers: { ETag: 'W/"h1"' } }));
    expect(await rest.getResource("r")).toEqual({ value: res, version_hash: "h1" });
    await rest.createResource(res);
    expect((await rest.updateResource("r", res, "h1")).version_hash).toBe("h1");
    await rest.deleteResource("r", "h1");
    await rest.deleteResource("r");
    expect(calls[2]?.headers["If-Match"]).toBe("h1");
    expect(calls[2]?.method).toBe("PUT");
    expect(calls[3]?.headers["If-Match"]).toBe("h1");
    expect(calls[4]?.headers["If-Match"]).toBeUndefined();
  });

  it("리소스 본문은 텍스트로 읽고 쓴다(If-Match, 412는 versionConflict)", async () => {
    let conflict = false;
    const { rest, calls } = fakeServer((c) => {
      if (c.method === "GET") return { text: "# 제목\n본문", headers: { ETag: '"h2"' } };
      return conflict
        ? {
            status: 412,
            body: { error: { code: "version_conflict", message: "충돌", details: { current_version_hash: "h9" } } },
          }
        : { body: {}, headers: { ETag: '"h3"' } };
    });
    expect(await rest.getResourceContent("r")).toEqual({ value: "# 제목\n본문", version_hash: "h2" });
    expect(await rest.putResourceContent("r", "새 본문", "h2", "text/markdown")).toEqual({
      version_hash: "h3",
    });
    expect(calls[1]?.rawBody).toBe("새 본문");
    expect(calls[1]?.headers["If-Match"]).toBe("h2");
    expect(calls[1]?.headers["Content-Type"]).toBe("text/markdown");
    conflict = true;
    const err = (await rest.putResourceContent("r", "x", "old").catch((e: unknown) => e)) as ApiError;
    expect(err.versionConflict?.current_version_hash).toBe("h9");
  });

  it("에이전트·설정 If-Match는 선택", async () => {
    const { rest, calls } = fakeServer();
    await rest.updateAgent("a", { id: "a" } as never);
    await rest.updateAgent("a", { id: "a" } as never, "h");
    await rest.putSettings({} as never, "s1");
    expect(calls[0]?.headers["If-Match"]).toBeUndefined();
    expect(calls[1]?.headers["If-Match"]).toBe("h");
    expect(calls[2]?.headers["If-Match"]).toBe("s1");
  });

  it("에이전트도 ETag를 함께 읽고 If-Match로 저장한다", async () => {
    const { rest, calls } = fakeServer(() => ({ body: { id: "a", name: "에이" }, headers: { ETag: '"a7"' } }));
    const got = await rest.getAgentVersioned("a");
    expect(got).toEqual({ value: { id: "a", name: "에이" }, version_hash: "a7" });
    const put = await rest.updateAgentVersioned("a", got.value, got.version_hash);
    expect(put.version_hash).toBe("a7");
    expect(calls.map((c) => `${c.method} ${c.path}`)).toEqual(["GET /agents/a", "PUT /agents/a"]);
    expect(calls[1]?.headers["If-Match"]).toBe("a7");
  });

  it("병합 전략 목록과 ETag를 함께 주는 설정 읽기·쓰기", async () => {
    const { rest, calls } = fakeServer((c) =>
      c.path === "/merge-strategies" ? { body: [{ id: "union" }] } : { body: { chat: {} }, headers: { ETag: '"s7"' } },
    );
    expect(await rest.listMergeStrategies()).toEqual([{ id: "union" }]);
    const got = await rest.getSettingsVersioned();
    expect(got).toEqual({ value: { chat: {} }, version_hash: "s7" });
    const put = await rest.putSettingsVersioned({} as never, "s7");
    expect(put.version_hash).toBe("s7");
    expect(calls.map((c) => `${c.method} ${c.path}`)).toEqual(["GET /merge-strategies", "GET /settings", "PUT /settings"]);
    expect(calls[2]?.headers["If-Match"]).toBe("s7");
  });

  it("서버 주소·토큰은 주입한 값만 쓴다(끝 슬래시 무시, 토큰 함수)", async () => {
    const urls: string[] = [];
    const heads: Array<Record<string, string>> = [];
    let tok = "A";
    const rest = createRestClient({
      baseUrl: "https://remote.example:9/",
      token: () => tok,
      fetch: (u, init) => {
        urls.push(u);
        heads.push(init?.headers as Record<string, string>);
        return Promise.resolve(new Response("[]"));
      },
    });
    await rest.listInteractions();
    tok = "B";
    await rest.listInteractions();
    expect(urls[0]).toBe("https://remote.example:9/api/v1/interactions");
    expect(heads.map((h) => h["X-Console-Token"])).toEqual(["A", "B"]);
  });
});

// ---- 가짜 소켓 ----
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
  open(): void {
    this.readyState = 1;
    this.onopen?.({});
  }
  push(msg: unknown): void {
    this.onmessage?.({ data: JSON.stringify(msg) });
  }
  closeWith(code: number): void {
    this.readyState = 3;
    this.onclose?.({ code });
  }
}

function setupWs(noReconnectCloseCodes?: readonly number[]) {
  const sockets: FakeSocket[] = [];
  const timers: Array<() => void> = [];
  const ws = createWsClient({
    baseUrl: "http://h",
    token: "T",
    webSocket: (u) => {
      const s = new FakeSocket(u);
      sockets.push(s);
      return s;
    },
    timers: {
      setTimeout: (fn) => {
        timers.push(fn);
        return fn;
      },
      clearTimeout: () => {},
    },
    ...(noReconnectCloseCodes ? { noReconnectCloseCodes } : {}),
  } satisfies WsClientOptions);
  return { ws, sockets, last: () => sockets[sockets.length - 1]!, timers };
}

const conv = (id: string, pending = 0) =>
  ({ type: "conversation.updated", payload: { conversation: { id, pending_interactions: pending } } }) as unknown as WsServerMessage;
const inter = (i: Interaction) =>
  ({ type: "interaction.updated", payload: { interaction: i } }) as unknown as WsServerMessage;

describe("WS 토픽 conversation·interactions", () => {
  it("interactions 토픽: subscribe 후 interaction.updated를 한 건씩 전달한다", () => {
    const { ws, last } = setupWs();
    const got: string[] = [];
    ws.subscribeInteractions((i) => got.push(`${i.id}:${i.status}`));
    last().open();
    expect(last().sent).toMatchObject([{ type: "subscribe", payload: { topic: "interactions" } }]);
    expect(last().sent[0]?.["payload"]).not.toHaveProperty("since_seq");
    last().push(inter(interaction("i1")));
    last().push(inter(interaction("i1", "answered")));
    last().push(conv("c1"));
    expect(got).toEqual(["i1:pending", "i1:answered"]);
  });

  it("conversation 토픽은 그 대화의 갱신만 받고, 같은 토픽 구독은 소켓 구독 하나로 합친다", () => {
    const { ws, last } = setupWs();
    const a: number[] = [];
    const b: number[] = [];
    const s1 = ws.subscribeConversation("c1", (c) => a.push(c.pending_interactions ?? 0));
    ws.subscribeConversation("c1", (c) => b.push(c.pending_interactions ?? 0));
    ws.subscribeConversation("c2", () => {
      throw new Error("c2는 받으면 안 됨");
    });
    last().open();
    expect(last().sent.map((m) => (m["payload"] as { topic: string }).topic)).toEqual([
      "conversation:c1",
      "conversation:c2",
    ]);
    last().push(conv("c1", 2));
    s1.unsubscribe();
    last().push(conv("c1", 3));
    expect(a).toEqual([2]);
    expect(b).toEqual([2, 3]);
  });

  it("마지막 구독자가 빠지면 unsubscribe를 보낸다", () => {
    const { ws, last } = setupWs();
    const sub = ws.subscribeInteractions(() => {});
    last().open();
    sub.unsubscribe();
    expect(last().sent[1]).toMatchObject({ type: "unsubscribe", payload: { topic: "interactions" } });
  });

  it("재접속하면 다시 구독한다", () => {
    const { ws, sockets, timers, last } = setupWs();
    ws.subscribeInteractions(() => {});
    ws.subscribeConversation("c1", () => {});
    last().open();
    last().closeWith(1006);
    timers.pop()?.();
    last().open();
    expect(sockets).toHaveLength(2);
    expect(last().sent.map((m) => (m["payload"] as { topic: string }).topic)).toEqual([
      "interactions",
      "conversation:c1",
    ]);
  });

  it("구독 오류(onError)는 해당 구독에 귀속된다", () => {
    const { ws, last } = setupWs();
    const onError = vi.fn();
    ws.subscribeInteractions(() => {}, { onError });
    last().open();
    last().push({ id: last().sent[0]?.["id"], type: "error", payload: { code: "forbidden", message: "x" } });
    expect(onError).toHaveBeenCalledWith({ code: "forbidden", message: "x" });
  });

  it("기본값은 인증 close 코드에서 재접속하지 않고, createClient도 옵션을 전달한다", () => {
    const { ws, sockets, last } = setupWs();
    ws.subscribeInteractions(() => {});
    last().open();
    last().closeWith(WS_CLOSE_FORBIDDEN);
    expect(ws.status).toBe("closed");
    expect(sockets).toHaveLength(1);
    const made: FakeSocket[] = [];
    const { ws: ws2 } = createClient({
      baseUrl: "http://h",
      noReconnectCloseCodes: [],
      timers: { setTimeout: () => 0, clearTimeout: () => {} },
      webSocket: (u) => {
        const s = new FakeSocket(u);
        made.push(s);
        return s;
      },
    });
    ws2.connect();
    made[0]!.open();
    made[0]!.closeWith(WS_CLOSE_UNAUTHORIZED);
    expect(ws2.status).toBe("reconnecting");
  });

  it("인증 close 코드 상수: 4401/4403, noReconnectCloseCodes로 넘기면 재접속하지 않는다", () => {
    expect(WS_CLOSE_UNAUTHORIZED).toBe(4401);
    expect(WS_CLOSE_FORBIDDEN).toBe(4403);
    expect([...WS_AUTH_CLOSE_CODES]).toEqual([4401, 4403]);
    const { ws, sockets, timers, last } = setupWs(WS_AUTH_CLOSE_CODES);
    ws.subscribeInteractions(() => {});
    last().open();
    last().closeWith(WS_CLOSE_UNAUTHORIZED);
    expect(ws.status).toBe("closed");
    expect(timers).toHaveLength(1); // 안정 타이머만 있고 재접속 타이머는 없다
    expect(sockets).toHaveLength(1);
  });
});
