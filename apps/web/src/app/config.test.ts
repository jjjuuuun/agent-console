import { describe, expect, it } from "vitest";
import { loadRuntimeConfig, resolveApiBaseUrl } from "./config";

const reply = (body: string, status = 200) => async () => new Response(body, { status });

describe("loadRuntimeConfig", () => {
  it("apiBaseUrl을 읽고 끝 슬래시를 정리한다", async () => {
    expect(await loadRuntimeConfig(reply('{"apiBaseUrl":"http://127.0.0.1:9000/"}'), "/config.json")).toEqual({ apiBaseUrl: "http://127.0.0.1:9000" });
  });
  it("파일이 없거나 깨졌거나 SPA 대체 HTML이거나 네트워크가 실패해도 오류가 아니다", async () => {
    expect(await loadRuntimeConfig(reply("", 404), "/c")).toEqual({});
    expect(await loadRuntimeConfig(reply("<html></html>"), "/c")).toEqual({});
    expect(await loadRuntimeConfig(async () => { throw new TypeError("net"); }, "/c")).toEqual({});
    expect(await loadRuntimeConfig(reply('{"apiBaseUrl":"javascript:alert(1)"}'), "/c")).toEqual({});
    expect(await loadRuntimeConfig(reply('{"apiBaseUrl":null}'), "/c")).toEqual({});
  });
});

describe("resolveApiBaseUrl", () => {
  it("설정 파일 → 빌드 변수 → 같은 출처 순서", () => {
    const origin = "http://page.test";
    expect(resolveApiBaseUrl({ config: { apiBaseUrl: "http://a" }, envUrl: "http://b", origin })).toBe("http://a");
    expect(resolveApiBaseUrl({ config: {}, envUrl: "http://b/", origin })).toBe("http://b");
    expect(resolveApiBaseUrl({ config: {}, envUrl: "", origin })).toBe(origin);
    expect(resolveApiBaseUrl({ config: {}, envUrl: undefined, origin })).toBe(origin);
  });
});
