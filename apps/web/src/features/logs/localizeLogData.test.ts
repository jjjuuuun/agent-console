import { describe, expect, it } from "vitest";
import type { LogDashboard, LogSourceInfo } from "@agent-console/contracts";
import { localizeDashboard, localizeSource, localizeTaxonomy } from "./localizeLogData";

const tr = (text: string) => ({ 플랫폼: "Platform", 토큰: "Tokens", 응답: "Reply" })[text] ?? text;

describe("localizeLogData", () => {
  it("출처 이름·설명을 옮기고 아이디는 그대로 둔다", () => {
    const info = { descriptor: { id: "p", title: "플랫폼", format: "jsonl", description: "응답" }, enabled: true } as LogSourceInfo;
    const out = localizeSource(info, tr);
    expect(out.descriptor).toMatchObject({ id: "p", title: "Platform", description: "Reply" });
  });
  it("분류 범주 이름과 대시보드 위젯 이름을 옮긴다", () => {
    expect(localizeTaxonomy({ categories: { a: { label: "응답" } } }, tr).categories?.["a"]?.label).toBe("Reply");
    const d = { id: "d", title: "토큰", widgets: [{ id: "w", kind: "table", title: "토큰", query: {} }] } as unknown as LogDashboard;
    const out = localizeDashboard(d, tr);
    expect(out.title).toBe("Tokens");
    expect(out.widgets?.[0]?.title).toBe("Tokens");
  });
});
