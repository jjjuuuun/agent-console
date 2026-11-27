import { createElement, type ReactNode } from "react";
import { renderHook } from "@testing-library/react";
import { ApiError } from "@agent-console/api-client";
import { applyServerCatalog } from "@agent-console/i18n";
import { ERROR_CODES } from "@agent-console/contracts";
import { describe, expect, it } from "vitest";
import { describeError, useDescribeError } from "./errors";
import { AppI18nProvider } from "../i18n/AppI18n";
import { createTestAppI18n } from "../testing/TestI18n";
import { koT } from "../testing/koText";
import { createAppTable } from "./appMessages";

const messages = createAppTable(koT("app"));

describe("describeError 코드별 문구", () => {
  it("project.config_readonly는 서버 영문 원문 대신 표의 한국어 문구", () => {
    const e = new ApiError(409, { code: ERROR_CODES.PROJECT_CONFIG_READONLY, message: "graph/ro3: the project folder is read-only" });
    const v = describeError(e, "실패", messages.errorByCode);
    expect(v.message).toBe(messages.errorByCode(ERROR_CODES.PROJECT_CONFIG_READONLY));
    expect(v.code).toBe("project.config_readonly");
  });
  it("표에 없는 코드는 서버 메시지 그대로", () => {
    expect(describeError(new ApiError(404, { code: "not_found", message: "없음" }), "x").message).toBe("없음");
  });
});

describe("useDescribeError 찾는 순서(I-17): 앱 errorByCode → 서버 issue → message", () => {
  const wrap = (i18n: ReturnType<typeof createTestAppI18n>) => ({ children }: { children: ReactNode }) => createElement(AppI18nProvider, { i18n, children });
  const make = (language: string) => {
    const i18n = createTestAppI18n(language);
    applyServerCatalog(i18n, { language: "en", text: {}, codes: { "zz.server_only": "Server code {thing}", [ERROR_CODES.PROJECT_CONFIG_READONLY]: "server text must lose" }, ns: {} });
    return i18n;
  };
  it("앱 표가 서버 묶음보다 먼저다", () => {
    const { result } = renderHook(() => useDescribeError(), { wrapper: wrap(make("en")) });
    const v = result.current(new ApiError(409, { code: ERROR_CODES.PROJECT_CONFIG_READONLY, message: "raw" }), "x");
    expect(v.message).not.toBe("server text must lose");
    expect(v.message).toContain("read-only");
  });
  it("앱 표에 없으면 서버 묶음의 틀을 details로 채운다", () => {
    const { result } = renderHook(() => useDescribeError(), { wrapper: wrap(make("en")) });
    expect(result.current(new ApiError(400, { code: "zz.server_only", message: "raw", details: { thing: "A" } }), "x").message).toBe("Server code A");
  });
  it("둘 다 없으면 서버 message", () => {
    const { result } = renderHook(() => useDescribeError(), { wrapper: wrap(make("en")) });
    expect(result.current(new ApiError(400, { code: "zz.unknown", message: "raw" }), "x").message).toBe("raw");
  });
});
