import { describe, expect, it } from "vitest";
import { ApiError, createRestClient, type FetchLike } from "./index";

interface Call {
  method: string;
  path: string;
  headers: Record<string, string>;
  body: unknown;
}
interface Reply {
  status?: number;
  body?: unknown;
  text?: string;
  headers?: Record<string, string>;
}
function server(respond: (c: Call) => Reply) {
  const calls: Call[] = [];
  const fn: FetchLike = (url, init = {}) => {
    const raw = init.body;
    calls.push({
      method: init.method ?? "GET",
      path: url.replace("http://h/api/v1", ""),
      headers: init.headers as Record<string, string>,
      body: raw,
    });
    const r = respond(calls[calls.length - 1]!);
    const body = r.text ?? (r.body === undefined ? null : JSON.stringify(r.body));
    return Promise.resolve(new Response(body, { status: r.status ?? 200, headers: r.headers }));
  };
  return { calls, rest: createRestClient({ baseUrl: "http://h", token: "T", fetch: fn }) };
}

describe("여러 파일 리소스 REST", () => {
  it("목록·읽기(ETag)·쓰기·삭제의 경로와 If-Match", async () => {
    const { rest, calls } = server((c): Reply => {
      if (c.method === "GET" && c.path.endsWith("/files")) return { body: [{ path: "a/b c.md", size: 1, sha256: "x" }] };
      if (c.method === "GET") return { text: "hello", headers: { "Content-Type": "text/plain; charset=utf-8", ETag: '"h1"' } };
      return { body: { id: "r", name: "r", type: "t" }, headers: { ETag: '"h2"' } };
    });
    expect(await rest.listResourceFiles("r 1")).toHaveLength(1);
    const read = await rest.readResourceFile("r", "a/b c.md");
    expect(read).toMatchObject({ text: "hello", version_hash: "h1", size: 5 });
    const put = await rest.putResourceFile("r", "a/b c.md", "x", "h1");
    expect(put.version_hash).toBe("h2");
    const bin = await rest.putResourceFile("r", "z.bin", new Uint8Array([1, 2]), "h2");
    expect(bin.version_hash).toBe("h2");
    await rest.deleteResourceFile("r", "a/b c.md", "h2");
    expect(calls.map((c) => `${c.method} ${c.path}`)).toEqual([
      "GET /resources/r%201/files",
      "GET /resources/r/files/a/b%20c.md",
      "PUT /resources/r/files/a/b%20c.md",
      "PUT /resources/r/files/z.bin",
      "DELETE /resources/r/files/a/b%20c.md",
    ]);
    expect(calls[2]!.headers["If-Match"]).toBe("h1");
    expect(calls[2]!.body).toBe("x");
    expect(calls[3]!.headers["Content-Type"]).toBe("application/octet-stream");
    expect(calls[4]!.headers["If-Match"]).toBe("h2");
  });

  it("412는 versionConflict", async () => {
    const { rest } = server(() => ({ status: 412, body: { error: { code: "version_conflict", message: "m" } } }));
    await expect(rest.putResourceFile("r", "a", "x", "old")).rejects.toBeInstanceOf(ApiError);
  });
});

describe("이어 가기·대기열 REST", () => {
  it("resume-options·resume·release", async () => {
    const { rest, calls } = server((c) => (c.path.endsWith("/release") ? { body: { position: 1, held: false } } : { body: { run_id: "r1", nodes: [] } }));
    await rest.getResumeOptions("r1");
    await rest.resumeRun("r1", ["n1", "n2"]);
    const q = await rest.releaseQueuedMessage("c1", "q1");
    expect(q.held).toBe(false);
    expect(calls.map((c) => `${c.method} ${c.path}`)).toEqual([
      "GET /runs/r1/resume-options",
      "POST /runs/r1/resume",
      "POST /conversations/c1/queue/q1/release",
    ]);
    expect(JSON.parse(calls[1]!.body as string)).toEqual({ node_ids: ["n1", "n2"] });
  });
});
