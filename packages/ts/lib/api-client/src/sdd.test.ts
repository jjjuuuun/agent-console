import { describe, expect, it } from "vitest";
import { ApiError, createRestIo, createSddClient, withSpace, type FetchLike } from "./index";

interface Call {
  method: string;
  path: string;
  body: unknown;
  headers: Record<string, string>;
}
function server(reply: (c: Call) => { status?: number; body?: unknown; headers?: Record<string, string> } = () => ({ body: {} })) {
  const calls: Call[] = [];
  const fetch: FetchLike = (url, init = {}) => {
    const raw = init.body;
    const call: Call = { method: init.method ?? "GET", path: url.replace("http://h/api/v1", ""), body: typeof raw === "string" ? JSON.parse(raw) : undefined, headers: (init.headers ?? {}) as Record<string, string> };
    calls.push(call);
    const r = reply(call);
    return Promise.resolve(new Response(r.status === 204 ? null : JSON.stringify(r.body ?? {}), { status: r.status ?? 200, headers: r.headers }));
  };
  const io = createRestIo({ baseUrl: "http://h", token: "T", fetch });
  return { calls, io };
}
const last = (calls: Call[]) => calls[calls.length - 1]!;

describe("스펙(SDD) REST", () => {
  it("목록·보기·저장·삭제 경로와 If-Match, 공간은 ?project=로 붙는다", async () => {
    const { io, calls } = server(() => ({ body: {}, headers: { ETag: '"v1"' } }));
    const sdd = createSddClient(withSpace(io, "p 1"));
    await sdd.listSpecs();
    expect(calls[0]).toMatchObject({ method: "GET", path: "/sdd/specs?project=p%201" });
    const got = await sdd.getSpec("a/b");
    expect(last(calls)).toMatchObject({ method: "GET", path: "/sdd/specs/a%2Fb?project=p%201" });
    expect(got.version_hash).toBe("v1");
    await sdd.putSpec("a", { kind: "k", id: "a", name: "n" }, "v1");
    expect(last(calls)).toMatchObject({ method: "PUT", path: "/sdd/specs/a?project=p%201" });
    expect(last(calls).headers["If-Match"]).toBe("v1");
    await sdd.deleteSpec("a", "v2");
    expect(last(calls)).toMatchObject({ method: "DELETE" });
    expect(last(calls).headers["If-Match"]).toBe("v2");
  });

  it("공간이 없으면 주소에 project가 붙지 않는다", async () => {
    const { io, calls } = server();
    await createSddClient(withSpace(io, null)).getSddInfo();
    expect(calls[0]).toMatchObject({ method: "GET", path: "/sdd/info" });
  });

  it("문서 본문: If-Match, 없을 때만 만들기는 If-None-Match: *", async () => {
    const { io, calls } = server(() => ({ body: { content: "x" }, headers: { ETag: '"c1"' } }));
    const sdd = createSddClient(io);
    const doc = await sdd.getSpecDocument("a", "d 1");
    expect(last(calls)).toMatchObject({ method: "GET", path: "/sdd/specs/a/documents/d%201" });
    expect(doc.version_hash).toBe("c1");
    await sdd.putSpecDocument("a", "d", "본문", { expectedHash: "c1" });
    expect(last(calls)).toMatchObject({ method: "PUT", body: { content: "본문" } });
    expect(last(calls).headers["If-Match"]).toBe("c1");
    await sdd.putSpecDocument("a", "d", "", { createOnly: true });
    expect(last(calls).headers["If-None-Match"]).toBe("*");
    expect(last(calls).headers["If-Match"]).toBeUndefined();
    await sdd.changeDocumentState("a", "d", { to: "t" });
    expect(last(calls)).toMatchObject({ method: "POST", path: "/sdd/specs/a/documents/d/state", body: { to: "t" } });
  });

  it("작업: 거르기는 같은 키 되풀이, 줄 고치기는 PATCH(expected_line_hash)", async () => {
    const { io, calls } = server(() => ({ body: [] }));
    const sdd = createSddClient(io);
    await sdd.listSpecTasks("a", { status: ["s1", "s2"], stage: ["g"], field: ["owner=x"], ready: true, q: "검색" });
    expect(last(calls).path).toBe("/sdd/specs/a/tasks?status=s1&status=s2&stage=g&field=owner%3Dx&ready=true&q=%EA%B2%80%EC%83%89");
    await sdd.listSpecTasks("a");
    expect(last(calls).path).toBe("/sdd/specs/a/tasks");
    await sdd.listSpecTasks("a", { q: "" });
    expect(last(calls).path).toBe("/sdd/specs/a/tasks");
    await sdd.patchSpecTask("a", "@d:1", { status: "s", expected_line_hash: "h" });
    expect(last(calls)).toMatchObject({ method: "PATCH", path: "/sdd/specs/a/tasks/%40d%3A1", body: { status: "s", expected_line_hash: "h" } });
  });

  it("그 밖의 경로: 가져오기·내보내기·검사·동작·틀", async () => {
    const { io, calls } = server();
    const sdd = createSddClient(io);
    await sdd.importSpec({ name: "n", files: ["a.md"] });
    expect(last(calls)).toMatchObject({ method: "POST", path: "/sdd/specs/import" });
    await sdd.listImportFiles("docs/x");
    expect(last(calls).path).toBe("/sdd/import/files?path=docs%2Fx");
    await sdd.listImportFiles();
    expect(last(calls).path).toBe("/sdd/import/files");
    await sdd.exportSpec("a", { to_dir: "out" });
    expect(last(calls)).toMatchObject({ method: "POST", path: "/sdd/specs/a/export", body: { to_dir: "out" } });
    await sdd.checkSpec("a", { rules: {} });
    expect(last(calls).path).toBe("/sdd/specs/a/check");
    await sdd.checkTemplate({ rules: {} });
    expect(last(calls).path).toBe("/sdd/templates/check");
    await sdd.listSpecTemplates();
    expect(last(calls).path).toBe("/sdd/templates");
    await sdd.runTaskAction("a", "T1", "int", "act", { x: 1 });
    expect(last(calls)).toMatchObject({ method: "POST", path: "/sdd/specs/a/tasks/T1/actions/int/act", body: { args: { x: 1 } } });
    await sdd.bulkStartTasks("a", { task_keys: ["T1"], action: { integration: "i", id: "d" } });
    expect(last(calls).path).toBe("/sdd/specs/a/bulk-start");
    await sdd.controlAutomation("a", "stop");
    expect(last(calls)).toMatchObject({ method: "POST", path: "/sdd/specs/a/automation/stop" });
    await sdd.saveSpecAsTemplate("a", { name: "t" });
    expect(last(calls).path).toBe("/sdd/specs/a/save-as-template");
  });

  it("실패는 ApiError로 코드와 details를 그대로 준다(task_changed)", async () => {
    const { io } = server(() => ({ status: 409, body: { error: { code: "sdd.task_changed", message: "바뀜", details: { task_key: "T1", line_hash: "h2" } } } }));
    const err = await createSddClient(io).patchSpecTask("a", "T1", { status: "s", expected_line_hash: "h" }).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).code).toBe("sdd.task_changed");
    expect((err as ApiError).details).toMatchObject({ task_key: "T1", line_hash: "h2" });
  });
});
