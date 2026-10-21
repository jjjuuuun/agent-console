import { describe, expect, it } from "vitest";
import { attachmentErrorsAt, hasMaskedSecret } from "./attachmentProblems";

describe("첨부 오류", () => {
  it("목록 위치 아래 오류를 첨부 번호별로 모은다", () => {
    const errors = [
      { path: "/resources/0/config_override/env/API_KEY", message: "평문" },
      { path: "/resources/2", message: "x" },
      { path: "/name", message: "무관" },
      { path: "/resources/0/mode", message: "y" },
    ];
    expect(attachmentErrorsAt(errors, "/resources")).toEqual({ 0: ["평문", "y"], 2: ["x"] });
    expect(attachmentErrorsAt(undefined, "/resources")).toEqual({});
  });
  it("가려진 비밀(***)을 찾는다", () => {
    expect(hasMaskedSecret({ ref: "r", config_override: { env: { K: "***" } } } as never)).toBe(true);
    expect(hasMaskedSecret({ ref: "r", config_override: { env: { K: "secret://k" } } } as never)).toBe(false);
    expect(hasMaskedSecret({ ref: "r" } as never)).toBe(false);
  });
});
