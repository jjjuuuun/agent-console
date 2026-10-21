import { describe, expect, it, vi } from "vitest";
import type { RestClient } from "@agent-console/api-client";
import type { ResourceTypeDescriptor } from "@agent-console/contracts";
import { createResourceDoc, newResourceDoc } from "./resourceLogic";

const docType = { id: "t-doc", title: "문서", content: { media_types: ["text/markdown"], editor: "markdown" } } as unknown as ResourceTypeDescriptor;
const cfgType = { id: "t-cfg", title: "설정", config_schema: { type: "object", properties: {} } } as unknown as ResourceTypeDescriptor;
const multiType = { id: "t-multi", title: "여럿", content: { media_types: ["text/plain"], multi_file: true } } as unknown as ResourceTypeDescriptor;

describe("newResourceDoc: 종류가 본문 모양을 정한다", () => {
  it("문서형은 빈 텍스트, 여러 파일형은 빈 목록, 설정형은 본문 없음", () => {
    expect(newResourceDoc(docType, { id: "a", name: "가" })).toMatchObject({ text: "", files: null, resource: { type: "t-doc", content: { file: "a.md", media_type: "text/markdown" } } });
    expect(newResourceDoc(multiType, { id: "a", name: "가" })).toMatchObject({ text: null, files: [] });
    expect(newResourceDoc(cfgType, { id: "a", name: "가" })).toMatchObject({ text: null, files: null });
  });
});

describe("createResourceDoc", () => {
  const fakeRest = (over: Record<string, unknown> = {}) =>
    ({
      createResource: vi.fn(async (r: unknown) => ({ value: r, version_hash: "v1" })),
      putResourceContent: vi.fn(async () => ({ value: "", version_hash: "v2" })),
      ...over,
    }) as unknown as RestClient & { createResource: ReturnType<typeof vi.fn>; putResourceContent: ReturnType<typeof vi.fn> };

  it("정의를 만들고, 본문이 비면 본문은 올리지 않는다", async () => {
    const rest = fakeRest();
    const out = await createResourceDoc(rest, newResourceDoc(docType, { id: "a", name: "가" }), [docType]);
    expect(rest.createResource).toHaveBeenCalledTimes(1);
    expect(rest.putResourceContent).not.toHaveBeenCalled();
    expect(out.bodyError).toBeUndefined();
  });

  it("본문이 있으면 정의 다음에 올린다", async () => {
    const rest = fakeRest();
    const doc = { ...newResourceDoc(docType, { id: "a", name: "가" }), text: "# 안녕" };
    await createResourceDoc(rest, doc, [docType]);
    expect(rest.putResourceContent).toHaveBeenCalledWith("a", "# 안녕", "v1", "text/markdown");
  });

  it("정의 생성이 실패하면 던진다", async () => {
    const rest = fakeRest({ createResource: vi.fn(async () => { throw new Error("중복"); }) });
    await expect(createResourceDoc(rest, newResourceDoc(docType, { id: "a", name: "가" }), [docType])).rejects.toThrow("중복");
  });

  it("본문 저장만 실패하면 던지지 않고 bodyError로 알린다(정의는 이미 있다)", async () => {
    const rest = fakeRest({ putResourceContent: vi.fn(async () => { throw new Error("디스크"); }) });
    const doc = { ...newResourceDoc(docType, { id: "a", name: "가" }), text: "x" };
    const out = await createResourceDoc(rest, doc, [docType]);
    expect(out.resource.id).toBe("a");
    expect(out.bodyError).toBeTruthy();
  });
});
