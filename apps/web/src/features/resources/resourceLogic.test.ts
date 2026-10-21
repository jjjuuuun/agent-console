import { describe, expect, it, vi } from "vitest";
import { ApiError } from "@agent-console/api-client";
import type { ImportCandidate, Resource, ResourceSummary, ResourceTypeDescriptor } from "@agent-console/contracts";
import { PartialSaveError, buildImportItems, countByType, editorLanguageOf, filterResources, hasDocument, loadResource, mediaTypeOf, resourceTabIds, saveResource } from "./resourceLogic";

const doc = { id: "t-doc", title: "문서종류", content: { editor: "x-lang", media_types: ["m/a", "m/b"] } } as unknown as ResourceTypeDescriptor;
const cfg = { id: "t-cfg", title: "설정종류" } as unknown as ResourceTypeDescriptor;
const dense = { kind: "resource", id: "r1", schema_version: 1, type: "t-doc", name: "이름", content: { file: "r1.txt", media_type: "m/b" } } as unknown as Resource;

describe("종류(디스크립터)가 탭 구성을 정한다", () => {
  it("문서형은 내용 탭이 있고 설정형은 설정 탭이 첫 탭이며 모르는 종류는 읽기 전용", () => {
    expect(resourceTabIds(doc)).toEqual(["content", "config", "usages"]);
    expect(resourceTabIds(cfg)).toEqual(["config", "usages"]);
    expect(resourceTabIds(undefined, dense)).toEqual(["content", "usages"]);
    expect(resourceTabIds(undefined, { ...dense, content: null } as Resource)).toEqual(["config", "usages"]);
    expect(hasDocument(doc)).toBe(true);
    expect(hasDocument(cfg)).toBe(false);
  });

  it("편집기 언어와 미디어 타입은 디스크립터·정의에서", () => {
    expect(editorLanguageOf(doc)).toBe("x-lang");
    expect(editorLanguageOf(undefined)).toBe("text");
    expect(mediaTypeOf(dense, doc)).toBe("m/b");
    expect(mediaTypeOf({ ...dense, content: null } as Resource, doc)).toBe("m/a");
  });
});

describe("읽기·저장", () => {
  it("저장 원문 정의를 그대로 받고 본문은 문서형일 때만 읽으며 본문이 없으면(404) 빈 문서", async () => {
    const rest = {
      getResource: vi.fn(async () => ({ value: dense, version_hash: "h1" })),
      getResourceContent: vi.fn(async () => { throw new ApiError(404, { code: "not_found", message: "x" }); }),
    };
    const got = await loadResource(rest as never, "r1", [doc, cfg]);
    expect(got.value.text).toBe("");
    expect(got.value.resource).toEqual({ kind: "resource", id: "r1", schema_version: 1, type: "t-doc", name: "이름", content: { file: "r1.txt", media_type: "m/b" } });
    expect(rest.getResourceContent).toHaveBeenCalledTimes(1);
    const none = await loadResource(rest as never, "r1", [{ ...cfg, id: "t-doc" } as ResourceTypeDescriptor]);
    expect(none.value.text).toBeNull();
  });

  it("정의와 본문이 모두 바뀌면 정의 -> 본문 순으로 같은 버전 흐름으로 저장한다", async () => {
    const rest = {
      updateResource: vi.fn(async () => ({ value: dense, version_hash: "h2" })),
      putResourceContent: vi.fn(async () => ({ version_hash: "h3" })),
    };
    const base = dense;
    const d = { resource: { ...base, name: "새" }, text: "본문", origin: { resource: base, text: "" } };
    const saved = await saveResource(rest as never, d, "h1", [doc]);
    expect(rest.updateResource).toHaveBeenCalledWith("r1", expect.objectContaining({ name: "새" }), "h1");
    expect(rest.putResourceContent).toHaveBeenCalledWith("r1", "본문", "h2", "m/b");
    expect(saved.version_hash).toBe("h3");
    expect(saved.value.origin.text).toBe("본문");
  });

  it("본문만 바뀌면 정의는 보내지 않고, 본문 저장이 실패하면 어느 쪽이 실패했는지 알린다", async () => {
    const rest = { updateResource: vi.fn(), putResourceContent: vi.fn(async () => { throw new Error("디스크"); }) };
    const base = dense;
    const d = { resource: base, text: "본문", origin: { resource: base, text: "" } };
    await expect(saveResource(rest as never, d, "h1", [doc])).rejects.toMatchObject({ failed: "content" });
    expect(rest.updateResource).not.toHaveBeenCalled();
    const d2 = { resource: { ...base, name: "새" }, text: "본문", origin: { resource: base, text: "" } };
    const rest2 = { updateResource: vi.fn(async () => ({ value: dense, version_hash: "h2" })), putResourceContent: vi.fn(async () => { throw new Error("디스크"); }) };
    const err = await saveResource(rest2 as never, d2, "h1", [doc]).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(PartialSaveError);
  });

  it("버전 충돌(412)은 그대로 올려 보낸다", async () => {
    const conflict = new ApiError(412, { code: "version_conflict", message: "x", details: { current_version_hash: "h9" } });
    const rest = { updateResource: vi.fn(async () => { throw conflict; }), putResourceContent: vi.fn() };
    const base = dense;
    await expect(saveResource(rest as never, { resource: { ...base, name: "새" }, text: "a", origin: { resource: base, text: "a" } }, "h1", [doc])).rejects.toBe(conflict);
  });
});

describe("목록과 가져오기", () => {
  const rows = [
    { id: "a", type: "t1", name: "알파", description: "첫째" },
    { id: "b", type: "t2", name: "베타" },
  ] as unknown as ResourceSummary[];
  it("종류별 개수와 필터", () => {
    expect([...countByType(rows)]).toEqual([["t1", 1], ["t2", 1]]);
    expect(filterResources(rows, { typeId: "t2", query: "" }).map((r) => r.id)).toEqual(["b"]);
    expect(filterResources(rows, { typeId: null, query: "첫째" }).map((r) => r.id)).toEqual(["a"]);
    expect(filterResources(rows, { typeId: null, query: "", onlyIds: new Set(["a"]) }).map((r) => r.id)).toEqual(["a"]);
  });

  it("선택한 후보만 요청하고 충돌 후보는 고른 처리를, 아니면 새 이름으로", () => {
    const cands = [{ id: "c1", conflict: true }, { id: "c2" }, { id: "c3" }] as ImportCandidate[];
    expect(buildImportItems(cands, new Set(["c1", "c2"]), { c1: "skip" })).toEqual([
      { candidate_id: "c1", on_conflict: "skip" },
      { candidate_id: "c2", on_conflict: "rename" },
    ]);
  });
});

import { plainSecretPaths, secretFieldsOf, toConfigErrors } from "./resourceLogic";

describe("비밀 필드(R13.6)", () => {
  const schema = { properties: { name: { type: "string" }, vars: { type: "object", description: "값은 secret://이름 참조만." }, hdr: { type: "object", description: "secret://" } } };
  it("스키마 설명이 secret://를 말하는 속성만 비밀 필드로 본다(키 이름 하드코딩 없음)", () => {
    expect(secretFieldsOf(schema)).toEqual(["vars", "hdr"]);
    expect(secretFieldsOf(undefined)).toEqual([]);
  });
  it("x-secret 주석이 있으면 설명 문구와 무관하게 그 속성(값 스키마 포함)만 비밀 필드", () => {
    const annotated = { properties: { env: { type: "object", additionalProperties: { type: "string", "x-secret": true } }, note: { type: "string", description: "secret:// 아님" }, tok: { type: "string", "x-secret": true } } };
    expect(secretFieldsOf(annotated)).toEqual(["env", "tok"]);
  });
  it("secret://로 시작하지 않는 값의 위치만 알리고 값은 싣지 않는다", () => {
    const paths = plainSecretPaths({ name: "n", vars: { A: "sk-live-1", B: "secret://b", C: "" }, hdr: { "x/y": "plain" } }, ["vars", "hdr"]);
    expect(paths).toEqual(["/vars/A", "/hdr/x~1y"]);
    expect(JSON.stringify(paths)).not.toContain("sk-live");
  });
  it("서버 422 이슈 경로는 /config 기준에서 폼 기준으로", () => {
    expect(toConfigErrors([{ path: "/config/vars/A", message: "m" }, { path: "/name", message: "x" }])).toEqual([{ path: "/vars/A", message: "m" }]);
  });
});
