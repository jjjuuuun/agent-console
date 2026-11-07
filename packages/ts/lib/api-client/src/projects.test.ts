import { describe, expect, it } from "vitest";
import { ApiError, createRestClient, createSpaceRestClient, withSpace, withQueryParam, type FetchLike, type RestIo } from "./index";

interface Call {
  method: string;
  path: string;
  body: unknown;
  headers: Record<string, string>;
  signal: AbortSignal | undefined;
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
      signal: init.signal ?? undefined,
    };
    calls.push(call);
    if (call.signal?.aborted === true) return Promise.reject(new DOMException("aborted", "AbortError"));
    const r = reply(call);
    return Promise.resolve(new Response(r.status === 204 ? null : JSON.stringify(r.body ?? {}), { status: r.status ?? 200, headers: r.headers }));
  };
  const options = { baseUrl: "http://h", token: "T", fetch };
  return { calls, options, rest: createRestClient(options) };
}
const last = (calls: Call[]) => calls[calls.length - 1]!;

describe("프로젝트 2 REST", () => {
  it("등록·조회·수정·해제 경로와 If-Match", async () => {
    const { rest, calls } = server(() => ({ body: { project: { id: "a" }, status: "ready" }, headers: { ETag: '"h1"' } }));
    await rest.listProjects();
    expect(calls[0]).toMatchObject({ method: "GET", path: "/projects" });
    const got = await rest.getProjectVersioned("a/b");
    expect(last(calls)).toMatchObject({ method: "GET", path: "/projects/a%2Fb" });
    expect(got.version_hash).toBe("h1");
    await rest.createProject({ folder: "/x" });
    expect(last(calls)).toMatchObject({ method: "POST", path: "/projects", body: { folder: "/x" } });
    await rest.updateProject("a", { archived: false }, "h1");
    expect(last(calls)).toMatchObject({ method: "PUT", path: "/projects/a", body: { archived: false }, headers: { "If-Match": "h1" } });
    await rest.updateProject("a", { name: "n" });
    expect(last(calls).headers["If-Match"]).toBeUndefined();
    await rest.unregisterProject("a", "h2");
    expect(last(calls)).toMatchObject({ method: "DELETE", path: "/projects/a", headers: { "If-Match": "h2" } });
  });

  it("가져오기·내보내기는 질의 project·target·source를 넘기고, 생략하면 주소가 그대로다 (33o)", async () => {
    const { rest, calls } = server(() => ({ body: { candidates: [], items: [] } }));
    await rest.previewImport({ source: "s" }, { project: "p 1", target: "library" });
    expect(last(calls).path).toBe("/resources/import/preview?project=p%201&target=library");
    await rest.importResources({ source: "s", items: [] }, { project: "p" });
    expect(last(calls).path).toBe("/resources/import?project=p");
    await rest.importResources({ source: "s", items: [] });
    expect(last(calls).path).toBe("/resources/import");
    await rest.planExport({ format: "f", items: [] } as never, { project: "p", source: "library" });
    expect(last(calls).path).toBe("/exports/plan?project=p&source=library");
    await rest.writeExport({} as never, { project: "p" });
    expect(last(calls).path).toBe("/exports/write?project=p");
    await rest.planExport({ format: "f", items: [] } as never);
    expect(last(calls).path).toBe("/exports/plan");
  });

  it("설정 파일 다시 만들기·.gitignore 덧붙이기 경로", async () => {
    const { rest, calls } = server();
    await rest.resetProjectManifest("a/b", { name: "n", description: "d" });
    expect(last(calls)).toMatchObject({ method: "POST", path: "/projects/a%2Fb/manifest/reset", body: { name: "n", description: "d" } });
    await rest.appendProjectGitignore("a");
    expect(last(calls)).toMatchObject({ method: "POST", path: "/projects/a/gitignore/append" });
  });

  it("폴더 확인·만들기·목록·고르는 방법", async () => {
    const { rest, calls } = server();
    await rest.checkFolder({ path: "/x", exclude_project_id: "p1" });
    expect(last(calls)).toMatchObject({ method: "POST", path: "/projects/folders/check", body: { path: "/x", exclude_project_id: "p1" } });
    await rest.createFolder("/x/new");
    expect(last(calls)).toMatchObject({ path: "/projects/folders/check", body: { path: "/x/new", create: true } });
    await rest.listFolders({ path: "/a b", hidden: true });
    expect(last(calls)).toMatchObject({ method: "GET", path: "/projects/folders?path=%2Fa%20b&hidden=true" });
    await rest.listFolders();
    expect(last(calls).path).toBe("/projects/folders");
    await rest.getFolderCapabilities();
    expect(last(calls)).toMatchObject({ method: "GET", path: "/projects/folders/capabilities" });
  });

  it("OS 선택 창: 요청 본문과 AbortSignal 전달, abort하면 끊김", async () => {
    const { rest, calls } = server(() => ({ body: { status: "picked", path: "/p" } }));
    const ac = new AbortController();
    const res = await rest.pickFolder({ initial: "/home", title: "t" }, { signal: ac.signal });
    expect(res.status).toBe("picked");
    expect(last(calls)).toMatchObject({ method: "POST", path: "/projects/folders/pick", body: { initial: "/home", title: "t" } });
    expect(last(calls).signal).toBe(ac.signal);
    await rest.pickFolder();
    expect(last(calls).body).toEqual({});
    expect(last(calls).signal).toBeUndefined();
    ac.abort();
    await expect(rest.pickFolder({}, { signal: ac.signal })).rejects.toBeInstanceOf(ApiError);
  });

  it("복사 계획·적용·옛 기록 계획", async () => {
    const { rest, calls } = server();
    const req = { source: { project_id: null }, target: { project_id: "p1" }, items: [{ kind: "k", id: "a" }] };
    await rest.planCopy({ ...req, include_references: true });
    expect(last(calls)).toMatchObject({ method: "POST", path: "/projects/copy/plan", body: { ...req, include_references: true } });
    await rest.applyCopy({ source: req.source, target: req.target, items: [{ kind: "k", id: "a", action: "copy", source_version: "v" }], remove_source: true });
    expect(last(calls)).toMatchObject({ method: "POST", path: "/projects/copy/apply" });
    await rest.planLegacyCopy("p/1");
    expect(last(calls)).toMatchObject({ method: "POST", path: "/projects/p%2F1/legacy/plan" });
  });

  it("메모리 복사 · 기록 개수 · 프로젝트에 넣기", async () => {
    const { rest, calls } = server();
    await rest.copyMemory({ source: { project_id: null }, target: { project_id: "p1" } });
    expect(last(calls)).toMatchObject({ method: "POST", path: "/memory/copy" });
    await rest.getRunProjectCounts();
    expect(last(calls)).toMatchObject({ method: "GET", path: "/runs/project-counts" });
    await rest.assignRunsToProject({ to: "p1", from_null: true });
    expect(last(calls)).toMatchObject({ method: "POST", path: "/runs/assign-project", body: { to: "p1", from_null: true } });
    await rest.getConversationProjectCounts();
    expect(last(calls)).toMatchObject({ method: "GET", path: "/conversations/project-counts" });
    await rest.assignConversationsToProject({ to: "p1", ids: ["c1"] });
    expect(last(calls)).toMatchObject({ method: "POST", path: "/conversations/assign-project", body: { to: "p1", ids: ["c1"] } });
  });

  it("목록 질의 project·source (없으면 보내지 않는다)", async () => {
    const { rest, calls } = server(() => ({ body: [] }));
    await rest.listRuns({ project: "p1", source: "app" });
    expect(last(calls).path).toBe("/runs?project=p1&source=app");
    await rest.listRuns();
    expect(last(calls).path).toBe("/runs");
    await rest.listConversations({ project: "p1" });
    expect(last(calls).path).toBe("/conversations?project=p1");
  });
});

describe("공간 인자 (?project=)", () => {
  it("withQueryParam: 질의가 있으면 &, 이미 있으면 그대로", () => {
    expect(withQueryParam("/agents", "project", "a b")).toBe("/agents?project=a%20b");
    expect(withQueryParam("/graphs?validate=false", "project", "p")).toBe("/graphs?validate=false&project=p");
    expect(withQueryParam("/graphs?project=x", "project", "p")).toBe("/graphs?project=x");
  });

  it("공간 인자가 없으면 지금 요청과 같은 주소 (회귀)", async () => {
    const plain = server();
    const library = server();
    const spaced = createSpaceRestClient(library.options, null);
    await Promise.all([plain.rest.listAgents(), plain.rest.getGraph("g"), plain.rest.listMemoryEntries({ q: "x" })]);
    await Promise.all([spaced.listAgents(), spaced.getGraph("g"), spaced.listMemoryEntries({ q: "x" })]);
    expect(library.calls.map((c) => [c.method, c.path])).toEqual(plain.calls.map((c) => [c.method, c.path]));
    for (const none of [undefined, ""]) {
      const io = {} as RestIo;
      expect(withSpace(io, none)).toBe(io);
    }
  });

  it("프로젝트 공간: 정의·버전·메모리 모든 요청에 project가 붙는다", async () => {
    const { options, calls } = server(() => ({ body: [] }));
    const space = createSpaceRestClient(options, "p 1");
    await space.listAgents();
    await space.updateGraph("g", { id: "g" } as never, "h");
    await space.listGraphVersions("g");
    await space.listMemoryEntries({ q: "x", limit: 5 });
    await space.copyMemory({ source: { project_id: "p 1" }, target: { project_id: null } });
    expect(calls.map((c) => [c.method, c.path])).toEqual([
      ["GET", "/agents?project=p%201"],
      ["PUT", "/graphs/g?project=p%201"],
      ["GET", "/graphs/g/versions?project=p%201"],
      ["GET", expect.stringMatching(/^\/memory\/entries\?.*q=x.*&project=p%201$/)],
      ["POST", "/memory/copy?project=p%201"],
    ]);
    expect(calls[1]!.headers["If-Match"]).toBe("h");
  });

  it("프로젝트 경로는 공간 인자 없이 (rest 클라이언트는 공간을 모른다)", async () => {
    const { rest, calls } = server();
    await rest.listProjects();
    expect(calls[0]!.path).toBe("/projects");
  });
});

describe("복사 종류·항목 (6R.20a)", () => {
  it("공용은 project 질의 없이, 프로젝트는 ?project=로 종류와 항목을 읽는다", async () => {
    const { rest, calls } = (() => {
      const calls: string[] = [];
      const fetch: FetchLike = (url) => {
        calls.push(url.replace("http://h/api/v1", ""));
        return Promise.resolve(new Response("[]", { status: 200 }));
      };
      return { rest: createRestClient({ baseUrl: "http://h", token: "T", fetch }), calls };
    })();
    await rest.listCopyKinds(null);
    await rest.listCopyKinds("p 1");
    await rest.listCopyItems(null, "zz-kind");
    await rest.listCopyItems("p 1");
    expect(calls).toEqual(["/projects/copy/kinds", "/projects/copy/kinds?project=p%201", "/projects/copy/items?kind=zz-kind", "/projects/copy/items?project=p%201"]);
  });
});

describe("프로젝트 사본 항목 삭제 (요청 11/07 후속)", () => {
  it("DELETE /projects/copy/items/{kind}/{id}?project= — 경로 인코딩과 선택 If-Match", async () => {
    const calls: { url: string; method: string; ifMatch: string | undefined }[] = [];
    const fetch: FetchLike = (url, init) => {
      const h = new Headers((init as RequestInit | undefined)?.headers);
      calls.push({ url: url.replace("http://h/api/v1", ""), method: String((init as RequestInit | undefined)?.method), ifMatch: h.get("If-Match") ?? undefined });
      return Promise.resolve(new Response(null, { status: 204 }));
    };
    const rest = createRestClient({ baseUrl: "http://h", token: "T", fetch });
    await rest.deleteCopyItem("p 1", "zz-kind", "a/b");
    await rest.deleteCopyItem("p1", "zz-kind", "x", { ifMatch: "h1" });
    expect(calls[0]).toEqual({ url: "/projects/copy/items/zz-kind/a%2Fb?project=p%201", method: "DELETE", ifMatch: undefined });
    expect(calls[1]).toEqual({ url: "/projects/copy/items/zz-kind/x?project=p1", method: "DELETE", ifMatch: "h1" });
  });
});

describe("대화 단위 호출의 ?project= (요청 11/07)", () => {
  it("project를 주면 상세·수정·삭제·턴·보내기·대기열 경로에 붙고, 생략하면 주소가 그대로다", async () => {
    const { rest, calls } = server(() => ({ body: { id: "c1" } }));
    await rest.getConversation("c1", "p1");
    expect(last(calls).path).toBe("/conversations/c1?project=p1");
    await rest.getConversation("c1");
    expect(last(calls).path).toBe("/conversations/c1");
    await rest.locateConversation("c/1");
    expect(last(calls)).toMatchObject({ method: "GET", path: "/conversations/c%2F1/locate" });
    await rest.updateConversation("c1", { title: "t" }, "p1");
    expect(last(calls)).toMatchObject({ method: "PATCH", path: "/conversations/c1?project=p1" });
    await rest.deleteConversation("c1", "p1");
    expect(last(calls)).toMatchObject({ method: "DELETE", path: "/conversations/c1?project=p1" });
    await rest.listTurns("c1", { limit: 5, project: "p1" });
    expect(last(calls).path).toBe("/conversations/c1/turns?limit=5&project=p1");
    await rest.postMessage("c1", { text: "x" }, "p1");
    expect(last(calls).path).toBe("/conversations/c1/messages?project=p1");
    await rest.listQueue("c1", "p1");
    expect(last(calls).path).toBe("/conversations/c1/queue?project=p1");
    await rest.cancelQueuedMessage("c1", "q1", "p1");
    expect(last(calls).path).toBe("/conversations/c1/queue/q1?project=p1");
    await rest.releaseQueuedMessage("c1", "q1", "p1");
    expect(last(calls).path).toBe("/conversations/c1/queue/q1/release?project=p1");
  });
});
