import { describe, expect, it } from "vitest";
import { ApiError, createRestIo, createWikiClient, withSpace, type FetchLike } from "./index";

interface Call {
  method: string;
  path: string;
  body: unknown;
  rawBody: unknown;
  headers: Record<string, string>;
}
function server(reply: (c: Call) => { status?: number; body?: unknown; text?: string; headers?: Record<string, string> } = () => ({ body: {} })) {
  const calls: Call[] = [];
  const fetch: FetchLike = (url, init = {}) => {
    const raw = init.body;
    const call: Call = { method: init.method ?? "GET", path: url.replace("http://h/api/v1", ""), body: typeof raw === "string" ? safeJson(raw) : undefined, rawBody: raw, headers: (init.headers ?? {}) as Record<string, string> };
    calls.push(call);
    const r = reply(call);
    const text = r.text ?? JSON.stringify(r.body ?? {});
    return Promise.resolve(new Response(r.status === 204 ? null : text, { status: r.status ?? 200, headers: r.headers }));
  };
  const io = createRestIo({ baseUrl: "http://h", token: "T", fetch });
  return { calls, io };
}
function safeJson(s: string): unknown {
  try {
    return JSON.parse(s);
  } catch {
    return undefined;
  }
}
const last = (calls: Call[]) => calls[calls.length - 1]!;

describe("위키 REST", () => {
  it("공간은 ?project=로 붙고, 없으면 붙지 않는다", async () => {
    const { io, calls } = server();
    await createWikiClient(withSpace(io, "p 1")).listWikis();
    expect(calls[0]).toMatchObject({ method: "GET", path: "/wiki/wikis?project=p%201" });
    await createWikiClient(withSpace(io, null)).getWikiInfo();
    expect(last(calls)).toMatchObject({ method: "GET", path: "/wiki/info" });
  });

  it("페이지 경로는 구분자 /를 유지하고 나머지를 인코딩한다(공백·# 포함)", async () => {
    const { io, calls } = server(() => ({ body: {}, headers: { ETag: '"h1"' } }));
    const wiki = createWikiClient(io);
    const got = await wiki.getWikiPage("w 1", "a b/c#d/한글");
    expect(last(calls).path).toBe("/wiki/wikis/w%201/pages/a%20b/c%23d/%ED%95%9C%EA%B8%80");
    expect(got.version_hash).toBe("h1");
  });

  it("쓰기: 있는 페이지는 If-Match, 새 페이지는 If-None-Match: *", async () => {
    const { io, calls } = server(() => ({ body: {}, headers: { ETag: '"h2"' } }));
    const wiki = createWikiClient(io);
    await wiki.putWikiPage("w", "p", { content: "x" }, { expectedHash: "h1" });
    expect(last(calls)).toMatchObject({ method: "PUT", body: { content: "x" } });
    expect(last(calls).headers["If-Match"]).toBe("h1");
    await wiki.putWikiPage("w", "p", { content: "x" }, { createOnly: true });
    expect(last(calls).headers["If-None-Match"]).toBe("*");
    expect(last(calls).headers["If-Match"]).toBeUndefined();
  });

  it("규칙 경고 헤더(X-Console-Issues)는 Versioned.issues로 온다", async () => {
    const issues = [{ severity: "warning", code: "wiki.rule_warning", message: "경고", rule_id: "r1" }];
    const { io } = server(() => ({ body: {}, headers: { ETag: '"h"', "X-Console-Issues": JSON.stringify(issues) } }));
    const r = await createWikiClient(io).putWikiPage("w", "p", { content: "x" }, { expectedHash: "h" });
    expect(r.issues?.[0]?.message).toBe("경고");
  });

  it("지우기·이름 바꾸기·미리보기·되돌리기·링크 글자·틀 채우기 경로와 본문", async () => {
    const { io, calls } = server();
    const wiki = createWikiClient(io);
    await wiki.deleteWikiPage("w", "a/b", "h1");
    expect(last(calls)).toMatchObject({ method: "DELETE", path: "/wiki/wikis/w/pages/a/b" });
    expect(last(calls).headers["If-Match"]).toBe("h1");
    await wiki.moveWikiPage("w", "a", { to: "b", rewrite_links: true, dry_run: true });
    expect(last(calls)).toMatchObject({ method: "POST", path: "/wiki/wikis/w/pages/a/move", body: { to: "b", rewrite_links: true, dry_run: true } });
    await wiki.previewWikiPage("w", "a", "본문");
    expect(last(calls)).toMatchObject({ method: "POST", path: "/wiki/wikis/w/pages/a/preview", body: { content: "본문" } });
    await wiki.restoreWikiPage("w", "a", { version: 3 });
    expect(last(calls)).toMatchObject({ method: "POST", path: "/wiki/wikis/w/pages/a/restore", body: { version: 3 } });
    await wiki.getWikiLinkText("w", { from_page: "a", target: "b" });
    expect(last(calls)).toMatchObject({ path: "/wiki/wikis/w/link-text", body: { from_page: "a", target: "b" } });
    await wiki.renderWikiTemplate("w", "t 1", { title: "제목", values: {} });
    expect(last(calls).path).toBe("/wiki/wikis/w/templates/t%201/render");
  });

  it("기록: 목록은 limit 질의, 버전 본문은 text로 온다", async () => {
    const { io, calls } = server((c) => (c.path.includes("/history/") ? { text: "# 옛 본문", headers: { ETag: '"s1"', "Content-Type": "text/markdown" } } : { body: { items: [], pruned: false } }));
    const wiki = createWikiClient(io);
    await wiki.getWikiPageHistory("w", "a", 5);
    expect(last(calls).path).toBe("/wiki/wikis/w/pages/a/history?limit=5");
    const v = await wiki.getWikiPageVersion("w", "a", 2);
    expect(last(calls).path).toBe("/wiki/wikis/w/pages/a/history/2");
    expect(v.value).toBe("# 옛 본문");
    expect(v.version_hash).toBe("s1");
  });

  it("검색 태그는 같은 키를 되풀이하고, 최근 변경 op는 쉼표 목록이다", async () => {
    const { io, calls } = server();
    const wiki = createWikiClient(io);
    await wiki.searchWiki("w", { q: "한글", prefix: "dir", tags: ["a", "b"], limit: 5 });
    expect(last(calls).path).toBe("/wiki/wikis/w/search?q=%ED%95%9C%EA%B8%80&prefix=dir&tag=a&tag=b&limit=5");
    await wiki.listWikiChanges("w", { op: ["delete", "move"], limit: 10, cursor: "c1" });
    expect(last(calls).path).toBe("/wiki/wikis/w/changes?op=delete%2Cmove&limit=10&cursor=c1");
    await wiki.listSpaceWikiChanges({ authorRun: "r1" });
    expect(last(calls).path).toBe("/wiki/changes?author_run=r1");
    await wiki.getWikiGraph("w", { center: "a", depth: 2, limit: 50 });
    expect(last(calls).path).toBe("/wiki/wikis/w/graph?center=a&depth=2&limit=50");
  });

  it("zip: 내보내기는 POST, 가져오기는 본문이 zip이고 policy·dry_run이 질의로 간다", async () => {
    const { io, calls } = server((c) => (c.path.includes("/export") ? { text: "ZIPDATA", headers: { "Content-Type": "application/zip", "Content-Disposition": 'attachment; filename="w.zip"' } } : { body: { items: [], dry_run: true } }));
    const wiki = createWikiClient(io);
    const exported = await wiki.exportWiki("w");
    expect(last(calls)).toMatchObject({ method: "POST", path: "/wiki/wikis/w/export" });
    expect(exported.filename).toBe("w.zip");
    await wiki.importWiki("w", new Uint8Array([80, 75]), { policy: "rename", dryRun: true });
    expect(last(calls)).toMatchObject({ method: "POST", path: "/wiki/wikis/w/import?policy=rename&dry_run=true" });
    expect(last(calls).headers["Content-Type"]).toBe("application/zip");
    await wiki.importWiki("w", new Uint8Array([80, 75]));
    expect(last(calls).path).toBe("/wiki/wikis/w/import");
  });

  it("규칙 목록·검사 경로", async () => {
    const { io, calls } = server();
    const wiki = createWikiClient(withSpace(io, "p"));
    await wiki.listWikiRules();
    expect(last(calls).path).toBe("/wiki/rules?project=p");
    await wiki.checkWikiRules({ rules: { id: "r" } });
    expect(last(calls)).toMatchObject({ method: "POST", path: "/wiki/rules/check?project=p", body: { rules: { id: "r" } } });
  });

  it("서버 오류는 ApiError로 코드와 상세가 그대로 온다", async () => {
    const { io } = server(() => ({ status: 404, body: { error: { code: "wiki.page_not_found", message: "없음", details: { path: "a", has_history: true } } } }));
    const err = await createWikiClient(io).getWikiPage("w", "a").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).code).toBe("wiki.page_not_found");
    expect((err as ApiError).details["has_history"]).toBe(true);
  });
});
