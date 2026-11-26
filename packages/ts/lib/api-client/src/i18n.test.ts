import { describe, expect, it } from "vitest";
import { ApiError } from "./errors";
import { createRestClient, type FetchLike } from "./index";

function client(respond: (url: string) => { status: number; body?: unknown }) {
  const calls: string[] = [];
  const fetch: FetchLike = (url) => {
    calls.push(url);
    const r = respond(url);
    return Promise.resolve(new Response(r.body === undefined ? null : JSON.stringify(r.body), { status: r.status }));
  };
  return { rest: createRestClient({ baseUrl: "http://x", fetch }), calls };
}

describe("i18n 클라이언트", () => {
  it("언어 목록과 묶음을 읽는다", async () => {
    const { rest, calls } = client((url) =>
      url.endsWith("/i18n")
        ? { status: 200, body: { languages: [], default_language: "en", fallback_language: "en" } }
        : { status: 200, body: { language: "ko", text: {}, codes: {}, ns: {} } },
    );
    expect((await rest.getI18nInfo()).default_language).toBe("en");
    expect((await rest.getI18nCatalog("ko"))?.language).toBe("ko");
    expect(calls.map((c) => new URL(c).pathname)).toEqual(["/api/v1/i18n", "/api/v1/i18n/ko"]);
  });

  it("그 언어 묶음이 없으면(404) null, 그 밖의 오류는 던진다", async () => {
    const missing = client(() => ({ status: 404, body: { error: { code: "i18n.unknown_language", message: "x" } } }));
    expect(await missing.rest.getI18nCatalog("xx")).toBeNull();
    const broken = client(() => ({ status: 500, body: { error: { code: "internal", message: "x" } } }));
    await expect(broken.rest.getI18nCatalog("ko")).rejects.toBeInstanceOf(ApiError);
  });

  it("코드에 특수 문자가 있으면 인코딩한다", async () => {
    const { rest, calls } = client(() => ({ status: 200, body: { language: "a/b", text: {}, codes: {}, ns: {} } }));
    await rest.getI18nCatalog("a/b");
    expect(calls[0]).toContain("/i18n/a%2Fb");
  });
});
