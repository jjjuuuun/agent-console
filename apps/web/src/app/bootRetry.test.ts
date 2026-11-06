import { ApiError, NETWORK_ERROR_CODE } from "@agent-console/api-client";
import { describe, expect, it } from "vitest";
import { BootError } from "./boot";
import { BOOT_RETRY, bootRetryDelay, classifyBootFailure, shouldGiveUp } from "./bootRetry";

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
  it("연결 대기는 5분 한도, 준비 중(503)은 한도 없이, 치명 오류는 즉시 포기", () => {
    expect(BOOT_RETRY.giveUpMs).toBe(300_000);
    expect(shouldGiveUp(BOOT_RETRY, "unreachable", 200_000, 5000)).toBe(false);
    expect(shouldGiveUp(BOOT_RETRY, "unreachable", 299_000, 5000)).toBe(true);
    expect(shouldGiveUp(BOOT_RETRY, "not-ready", 10_000_000, 5000)).toBe(false);
    expect(shouldGiveUp(BOOT_RETRY, "fatal", 0, 0)).toBe(true);
  });
});
