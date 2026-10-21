import { describe, expect, it, vi } from "vitest";
import { ApiError } from "@agent-console/api-client";
import type { Resource, ResourceTypeDescriptor } from "@agent-console/contracts";
import { PartialSaveResult } from "../../definition/useDefinitionEditor";
import { checkPath, decodeUtf8, languageForFile, planFileChanges, removeEntries, renameEntries, totalSize, type FileEntry } from "./fileTreeLogic";
import { isMultiFile, loadResource, saveResource } from "./resourceLogic";

const f = (path: string, text: string | null = ""): FileEntry => ({ path, text, size: text?.length ?? 3 });

describe("경로 검사", () => {
  it("빈 값·절대·..·중복·금지 문자·예약 이름·끝 점을 막는다", () => {
    const ex = ["a/b.md", "x"];
    expect(checkPath("", ex)).toBe("empty");
    expect(checkPath("/abs", ex)).toBe("absolute");
    expect(checkPath("C:\\x", ex)).toBe("absolute");
    expect(checkPath("a/../b", ex)).toBe("dotdot");
    expect(checkPath("a/b.md", ex)).toBe("duplicate");
    expect(checkPath("a/b.md", ex, "a/b.md")).toBeNull();
    expect(checkPath("a?b", ex)).toBe("forbidden");
    expect(checkPath("dir/CON.txt", ex)).toBe("reserved");
    expect(checkPath("a/b.", ex)).toBe("trailing");
    expect(checkPath("x/y", ex)).toBe("folderConflict");
    expect(checkPath("a", ex)).toBe("folderConflict");
    expect(checkPath("new/dir/f.md", ex)).toBeNull();
  });
});

describe("초안 조작", () => {
  it("폴더 이름 바꾸기는 하위 경로를 모두 옮기고 개수를 센다", () => {
    const r = renameEntries([f("a/1"), f("a/b/2"), f("c")], "a", "z");
    expect(r.files.map((x) => x.path)).toEqual(["z/1", "z/b/2", "c"]);
    expect(r.moved).toBe(2);
    expect(removeEntries([f("a/1"), f("ab"), f("c")], "a").files.map((x) => x.path)).toEqual(["ab", "c"]);
  });

  it("변경 계획: 새 파일·수정만 올리고 사라진 것은 지운다(이름 바꾸기 = 올리기 + 지우기)", () => {
    const origin = [f("a", "1"), f("b", "2"), f("c", null)];
    const draft = [f("a", "1"), f("b", "수정"), f("d", "새"), f("c", null)];
    expect(planFileChanges(origin, draft)).toEqual({ puts: [f("b", "수정"), f("d", "새")], deletes: [] });
    expect(planFileChanges(origin, [f("a2", "1"), f("b", "2"), f("c", null)])).toEqual({ puts: [f("a2", "1")], deletes: ["a"] });
  });

  it("언어는 미디어 타입 -> 확장자 -> text, 합계와 UTF-8 판별", () => {
    expect(languageForFile("x.bin", "text/markdown; charset=utf-8")).toBe("markdown");
    expect(languageForFile("a/b.JSON")).toBe("json");
    expect(languageForFile("noext")).toBe("text");
    expect(totalSize([f("a", "가"), { path: "b", text: null, size: 10 }])).toBe(13);
    expect(decodeUtf8(new Uint8Array([0xff, 0xfe]))).toBeNull();
    expect(decodeUtf8(new TextEncoder().encode("가"))).toBe("가");
  });
});

const multi = { id: "t-any", title: "임의", content: { multi_file: true, editor: "markdown" } } as unknown as ResourceTypeDescriptor;
const base = { kind: "resource", id: "r1", type: "t-any", name: "이름" } as unknown as Resource;

describe("여러 파일 읽기·저장(종류 이름 없이 디스크립터로)", () => {
  it("multi_file이면 파일을 모두 읽는다", async () => {
    expect(isMultiFile(multi)).toBe(true);
    expect(isMultiFile({ ...multi, content: { editor: "x" } } as ResourceTypeDescriptor)).toBe(false);
    const rest = {
      getResource: vi.fn(async () => ({ value: base, version_hash: "h1" })),
      listResourceFiles: vi.fn(async () => [{ path: "b", size: 1, sha256: "x" }, { path: "a", size: 1, sha256: "y" }]),
      readResourceFile: vi.fn(async (_id: string, p: string) => ({ text: p === "a" ? "A" : null, contentType: "", size: 1, version_hash: "h1" })),
      getResourceContent: vi.fn(),
    };
    const got = await loadResource(rest as never, "r1", [multi]);
    expect(got.value.files?.map((x) => [x.path, x.text])).toEqual([["a", "A"], ["b", null]]);
    expect(got.value.text).toBeNull();
    expect(rest.getResourceContent).not.toHaveBeenCalled();
  });

  it("올리기마다 If-Match가 새 해시로 이어지고, 올리기가 모두 끝나야 지운다", async () => {
    const calls: string[] = [];
    const rest = {
      putResourceFile: vi.fn(async (_i: string, p: string, _c: unknown, h: string) => {
        calls.push(`put ${p} ${h}`);
        return { value: base, version_hash: `h-${p}` };
      }),
      deleteResourceFile: vi.fn(async (_i: string, p: string, h: string) => {
        calls.push(`del ${p} ${h}`);
        return { value: base, version_hash: "hz" };
      }),
    };
    const origin = [f("old", "x")];
    const doc = { resource: base, text: null, files: [f("n1", "x"), f("n2", "y")], origin: { resource: base, text: null, files: origin } };
    const saved = await saveResource(rest as never, doc, "h0", [multi]);
    expect(calls).toEqual(["put n1 h0", "put n2 h-n1", "del old h-n2"]);
    expect(saved.version_hash).toBe("hz");
    expect(saved.value.origin.files?.map((x) => x.path)).toEqual(["n1", "n2"]);
  });

  it("일부 실패: 성공한 것은 반영, 실패한 변경은 초안에 남고 서버 메시지가 붙으며 지우기는 하지 않는다", async () => {
    const rest = {
      putResourceFile: vi.fn(async (_i: string, p: string) => {
        if (p === "bad") throw new ApiError(413, { code: "too_large", message: "총량 초과" });
        return { value: base, version_hash: "h1" };
      }),
      deleteResourceFile: vi.fn(),
    };
    const doc = { resource: base, text: null, files: [f("ok", "1"), f("bad", "2")], origin: { resource: base, text: null, files: [f("old", "x")] } };
    const err = await saveResource(rest as never, doc, "h0", [multi]).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(PartialSaveResult);
    const partial = err as PartialSaveResult<typeof doc>;
    expect(partial.saved.version_hash).toBe("h1");
    expect(partial.saved.value.files?.map((x) => x.path).sort()).toEqual(["ok", "old"]);
    expect((partial.remaining as { fileErrors?: Record<string, string> }).fileErrors).toEqual({ bad: "총량 초과" });
    expect(rest.deleteResourceFile).not.toHaveBeenCalled();
  });

  it("412는 부분 저장이 아니라 그대로 던져 충돌로 다룬다", async () => {
    const conflict = new ApiError(412, { code: "version_conflict", message: "충돌", details: { current_version_hash: "h9", saved_at: 1 } });
    const rest = { putResourceFile: vi.fn(async () => { throw conflict; }) };
    const doc = { resource: base, text: null, files: [f("x", "1")], origin: { resource: base, text: null, files: [] } };
    await expect(saveResource(rest as never, doc, "h0", [multi])).rejects.toBe(conflict);
  });
});
