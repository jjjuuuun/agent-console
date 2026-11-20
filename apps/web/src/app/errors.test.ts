import { ApiError } from "@agent-console/api-client";
import { ERROR_CODES } from "@agent-console/contracts";
import { describe, expect, it } from "vitest";
import { describeError } from "./errors";
import { messages } from "./messages";

describe("describeError 코드별 문구", () => {
  it("project.config_readonly는 서버 영문 원문 대신 표의 한국어 문구", () => {
    const e = new ApiError(409, { code: ERROR_CODES.PROJECT_CONFIG_READONLY, message: "graph/ro3: the project folder is read-only" });
    const v = describeError(e, "실패");
    expect(v.message).toBe(messages.errorByCode[ERROR_CODES.PROJECT_CONFIG_READONLY]);
    expect(v.code).toBe("project.config_readonly");
  });
  it("표에 없는 코드는 서버 메시지 그대로", () => {
    expect(describeError(new ApiError(404, { code: "not_found", message: "없음" }), "x").message).toBe("없음");
  });
});
