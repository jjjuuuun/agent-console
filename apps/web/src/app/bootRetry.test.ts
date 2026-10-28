import { ApiError, NETWORK_ERROR_CODE } from "@agent-console/api-client";
import { describe, expect, it } from "vitest";
import { BootError } from "./boot";
import { BOOT_RETRY, bootRetryDelay, classifyBootFailure } from "./bootRetry";

const boot = (cause: unknown) => new BootError("http://x", cause, false);

describe("부팅 실패 분류", () => {
  it("503 not_ready는 준비 중, 연결 거부·프록시 5xx는 연결 대기, 그 밖은 즉시 오류", () => {
    expect(classifyBootFailure(boot(new ApiError(503, { code: "not_ready", message: "" })))).toBe("not-ready");
    expect(classifyBootFailure(boot(new ApiError(0, { code: NETWORK_ERROR_CODE, message: "" })))).toBe("unreachable");
    expect(classifyBootFailure(boot(new ApiError(502, { code: "x", message: "" })))).toBe("unreachable");
    expect(classifyBootFailure(boot(new ApiError(403, { code: "forbidden", message: "" })))).toBe("fatal");
    expect(classifyBootFailure(new Error("boom"))).toBe("fatal");
  });
  it("대기는 지수로 늘고 상한에서 멈춘다", () => {
    const d = [0, 1, 2, 3, 6].map((n) => bootRetryDelay(BOOT_RETRY, n));
    expect(d).toEqual([500, 1000, 2000, 4000, 5000]);
  });
});
