import { describe, expect, it } from "vitest";
import { ApiError, createRestClient, definitionBase, filenameFromDisposition, type FetchLike } from "./index";

interface Call {
  method: string;
  path: string;
  headers: Record<string, string>;
  body: unknown;
}
interface Reply {
  status?: number;
  body?: unknown;
  bytes?: Uint8Array;
  headers?: Record<string, string>;
}
function server(respond: (c: Call) => Reply) {
  const calls: Call[] = [];
  const fn: FetchLike = (url, init = {}) => {
    const raw = init.body;
    const call: Call = {
      method: init.method ?? "GET",
      path: url.replace("http://h/api/v1", ""),
      headers: init.headers as Record<string, string>,
      body: typeof raw === "string" ? JSON.parse(raw) : undefined,
    };
    calls.push(call);
    const r = respond(call);
    const body = r.bytes ?? (r.body === undefined ? null : JSON.stringify(r.body));
    return Promise.resolve(new Response(body as BodyInit | null, { status: r.status ?? 200, headers: r.headers }));
  };
  return { calls, rest: createRestClient({ baseUrl: "http://h", token: "T", fetch: fn }) };
}

describe("내보내기 REST", () => {
  it("형식 목록·미리보기·루트·쓰기의 메서드와 경로, 토큰 헤더", async () => {
    const { rest, calls } = server(() => ({ body: [] }));
    await rest.listExporters();
    await rest.planExport({ exporter: "x", items: [{ kind: "graph", id: "g" }], options: { a: 1 }, root: "r", subdir: "s" });
    await rest.listExportRoots();
    await rest.writeExport({ exporter: "x", root: "r", on_conflict: "fail" });
    expect(calls.map((c) => `${c.method} ${c.path}`)).toEqual([
      "GET /exporters",
      "POST /exports/plan",
      "GET /exports/roots",
      "POST /exports/write",
    ]);
    expect(calls[1]!.body).toEqual({ exporter: "x", items: [{ kind: "graph", id: "g" }], options: { a: 1 }, root: "r", subdir: "s" });
    expect(calls[2]!.headers["X-Console-Token"]).toBe("T");
  });

  it("zip은 토큰 헤더와 함께 받아 Blob과 파일 이름을 돌려준다(없으면 export.zip)", async () => {
    const { rest, calls } = server((c): Reply =>
      c.body && (c.body as { exporter: string }).exporter === "named"
        ? { bytes: new Uint8Array([80, 75, 3, 4]), headers: { "Content-Type": "application/zip", "Content-Disposition": 'attachment; filename="한글.zip"' } }
        : { bytes: new Uint8Array([1]), headers: { "Content-Type": "application/zip" } },
    );
    const a = await rest.downloadExportArchive({ exporter: "named" });
    expect(a.blob.size).toBe(4);
    expect(a.filename).toBe("한글.zip");
    expect((await rest.downloadExportArchive({ exporter: "other" })).filename).toBe("export.zip");
    expect(calls[0]!.headers["X-Console-Token"]).toBe("T");
  });

  it("archive 422·write 409는 서버 메시지와 details를 가진 ApiError", async () => {
    const { rest } = server((c) =>
      c.path === "/exports/archive"
        ? { status: 422, body: { error: { code: "validation_failed", message: "형식 오류" } } }
        : { status: 409, body: { error: { code: "already_exists", message: "있음", details: { paths: ["a.md"] } } } },
    );
    await expect(rest.downloadExportArchive({ exporter: "x" })).rejects.toMatchObject({ status: 422, message: "형식 오류" });
    const e = (await rest.writeExport({ exporter: "x", root: "r" }).catch((x: unknown) => x)) as ApiError;
    expect(e.status).toBe(409);
    expect(e.details["paths"]).toEqual(["a.md"]);
  });

  it("네트워크 실패는 ApiError(status 0)", async () => {
    const rest = createRestClient({ baseUrl: "http://h", fetch: () => Promise.reject(new Error("down")) });
    await expect(rest.downloadExportArchive({ exporter: "x" })).rejects.toMatchObject({ status: 0 });
  });
});

describe("버전 REST", () => {
  const base = definitionBase("/resources", "a b");
  it("경로: 목록·단건·비교(대상 생략 = 현재)·파일·복원 If-Match", async () => {
    const { rest, calls } = server((c) => (c.path.includes("/restore") ? { body: { kind: "k", id: "i", version_hash: "n", saved_at: 1 }, headers: { ETag: '"n"' } } : { body: [] }));
    expect(base).toBe("/resources/a%20b");
    await rest.listDefinitionVersions(base);
    await rest.getDefinitionVersion(base, "h1");
    await rest.diffDefinitionVersions(base, "h1");
    await rest.diffDefinitionVersions(base, "h1", "h2");
    await rest.listVersionFiles(base, "h1");
    const restored = await rest.restoreDefinitionVersion(base, "h1", { message: "m" }, "cur");
    await rest.restoreDefinitionVersion("/settings", "h1");
    expect(calls.map((c) => `${c.method} ${c.path}`)).toEqual([
      "GET /resources/a%20b/versions",
      "GET /resources/a%20b/versions/h1",
      "GET /resources/a%20b/versions/h1/diff",
      "GET /resources/a%20b/versions/h1/diff/h2",
      "GET /resources/a%20b/versions/h1/files",
      "POST /resources/a%20b/versions/h1/restore",
      "POST /settings/versions/h1/restore",
    ]);
    expect(calls[5]!.headers["If-Match"]).toBe("cur");
    expect(calls[5]!.body).toEqual({ message: "m" });
    expect(calls[6]!.headers["If-Match"]).toBeUndefined();
    expect(restored.version_hash).toBe("n");
  });

  it("복원 412는 versionConflict, 422는 issues를 details로 가진다", async () => {
    const { rest } = server((c) =>
      c.headers["If-Match"] === "old"
        ? { status: 412, body: { error: { code: "version_conflict", message: "충돌", details: { current_version_hash: "cur2" } } } }
        : { status: 422, body: { error: { code: "validation_failed", message: "검증", details: { issues: [{ path: "/a", message: "m" }] } } } },
    );
    const e1 = (await rest.restoreDefinitionVersion("/agents/x", "h", {}, "old").catch((x: unknown) => x)) as ApiError;
    expect(e1.versionConflict?.current_version_hash).toBe("cur2");
    const e2 = (await rest.restoreDefinitionVersion("/agents/x", "h", {}, "cur").catch((x: unknown) => x)) as ApiError;
    expect(e2.status).toBe(422);
    expect(e2.details["issues"]).toEqual([{ path: "/a", message: "m" }]);
  });

  it("본문 파일: 경로 구분자를 유지해 인코딩하고 텍스트/바이너리를 구분한다", async () => {
    const { rest, calls } = server((c) =>
      c.path.endsWith("bin.dat")
        ? { bytes: new Uint8Array([0, 1, 2]), headers: { "Content-Type": "application/octet-stream" } }
        : { bytes: new TextEncoder().encode("안녕"), headers: { "Content-Type": "text/plain; charset=utf-8" } },
    );
    const text = await rest.readVersionFile(base, "h1", "skills/my skill/SKILL.md");
    expect(calls[0]!.path).toBe("/resources/a%20b/versions/h1/files/skills/my%20skill/SKILL.md");
    expect(text.text).toBe("안녕");
    const bin = await rest.readVersionFile(base, "h1", "bin.dat");
    expect(bin.text).toBeNull();
    expect(bin.size).toBe(3);
  });
});

describe("filenameFromDisposition", () => {
  it.each([
    ['attachment; filename="a.zip"', "a.zip"],
    ["attachment; filename=a.zip", "a.zip"],
    ["attachment; filename*=UTF-8''%ED%95%9C.zip", "한.zip"],
    [null, undefined],
    ["attachment", undefined],
  ])("%s", (input, expected) => {
    expect(filenameFromDisposition(input)).toBe(expected);
  });
});

describe("X-Console-Issues 응답 헤더(저장은 하되 경고, design 3R.7)", () => {
  const issue = { severity: "warning", code: "resource.reserved_file_name", message: "예약 이름입니다", path: ".git/config" };
  it("파일·본문 저장 응답의 issues로 노출하고, 없거나 깨진 헤더는 무시한다", async () => {
    const { rest } = server((c): Reply => {
      if (c.path.endsWith("/content")) return { body: undefined, headers: { ETag: '"h2"', "X-Console-Issues": "{깨짐" } };
      if (c.path.includes("/files/bad")) return { body: { id: "r" }, headers: { ETag: '"h3"', "X-Console-Issues": "[]" } };
      return { body: { id: "r" }, headers: { ETag: '"h1"', "X-Console-Issues": JSON.stringify([issue]) } };
    });
    const withWarning = await rest.putResourceFile("r", ".git/config", new Uint8Array([1]), "h0");
    expect(withWarning.version_hash).toBe("h1");
    expect(withWarning.issues).toEqual([issue]);
    expect((await rest.putResourceFile("r", "bad", new Uint8Array([1]), "h0")).issues).toBeUndefined();
    const content = await rest.putResourceContent("r", "{}", "h0");
    expect(content.version_hash).toBe("h2");
    expect(content.issues).toBeUndefined();
  });
});
