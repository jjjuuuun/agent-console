import { describe, expect, it } from "vitest";
import * as api from "./index";
import { avatarColorIndex, formatCountdown, formatSeconds } from "./shared/util";

describe("공개 API", () => {
  it("핵심 컴포넌트와 기본 렌더러 표를 내보낸다", () => {
    for (const name of ["MessageList", "TurnView", "ReplyGroup", "ProgressStrip", "Composer", "InteractionCard", "Markdown"]) expect(typeof (api as Record<string, unknown>)[name]).toBe("function");
    expect(Object.keys(api.defaultRenderers).sort()).toEqual(["choices", "permission", "review"]);
  });
  it("유틸", () => {
    expect(formatSeconds(125)).toBe("2분 5초");
    expect(formatCountdown(288)).toBe("4:48");
    expect(avatarColorIndex("pl")).toBeGreaterThanOrEqual(1);
    expect(avatarColorIndex("pl")).toBeLessThanOrEqual(8);
  });
});
