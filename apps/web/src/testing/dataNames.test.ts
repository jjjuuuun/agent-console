import { describe, expect, it } from "vitest";
import { dataNameLiteral, findDataNameLiterals, isAllowedVariant } from "./dataNames";

describe("dataNameLiteral", () => {
  it("정확한 이름, 대소문자 변형, 접두·접미 변형을 잡는다", () => {
    const re = dataNameLiteral("hook");
    for (const bad of ['"hook"', "'Hook'", '"HOOK"', '"hook:pre"', "`mcp`".replace("mcp", "hook.call"), '"log_hook"', '"a/hook"']) expect(re.test(bad), bad).toBe(true);
  });
  it("구분자 없이 붙은 낱말·문장 속 낱말은 잡지 않는다", () => {
    const re = dataNameLiteral("hook");
    for (const ok of ['"hooked"', '"a hook b"', '"hooks"', '"webhook"']) expect(re.test(ok), ok).toBe(false);
  });
  it("점이 든 이름은 리터럴 점으로 비교한다", () => {
    expect(dataNameLiteral("tokens.total").test('"tokensXtotal"')).toBe(false);
    expect(dataNameLiteral("tokens.total").test('"tokens.total"')).toBe(true);
  });
});

describe("findDataNameLiterals / isAllowedVariant", () => {
  it("변형 리터럴 내용을 돌려준다", () => {
    expect(findDataNameLiterals(`const a = ["hook.", 'Hook:pre', "ok"];`, "hook")).toEqual(["hook.", "Hook:pre"]);
  });
  it("허용 목록은 파일과 리터럴이 모두 맞을 때만", () => {
    expect(isAllowedVariant("features/runs/ObserveTab.tsx", "tool_use_id")).toBe(true);
    expect(isAllowedVariant("features\\runs\\ObserveTab.tsx", "tool_use_id")).toBe(true);
    expect(isAllowedVariant("features/other/x.ts", "tool_use_id")).toBe(false);
    expect(isAllowedVariant("features/runs/ObserveTab.tsx", "other_id")).toBe(false);
    // 코드에서 사라진 부채 항목은 더 이상 허용되지 않는다
    expect(isAllowedVariant("features/runs/runsConfig.ts", "hook.")).toBe(false);
    expect(isAllowedVariant("features/runs/runsConfig.ts", "mcp.")).toBe(false);
  });
});
