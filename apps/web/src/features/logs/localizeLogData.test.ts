import { describe, expect, it } from "vitest";
import type { LogDashboard, LogEvent, LogSourceInfo } from "@agent-console/contracts";
import { localizeDashboard, localizeEvent, localizeSource, localizeTaxonomy } from "./localizeLogData";

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

describe("localizeEvent: 값이 섞인 제목·본문", () => {
  const render = (value: string, parts?: readonly { template: string; params?: Record<string, unknown> | undefined }[] | null) =>
    parts && parts.length > 0 ? parts.map((p) => (p.template === "세션 시작 {id}" ? `Session started ${String(p.params?.["id"])}` : value)).join(" ") : tr(value);
  it("text_templates의 /title 틀이 있으면 render로, 없으면 tr로 옮긴다", () => {
    const e = { uid: "u", title: "세션 시작 s-1", summary: "응답", text_templates: { "/title": [{ template: "세션 시작 {id}", params: { id: "s-1" } }] } } as unknown as LogEvent;
    const out = localizeEvent(e, tr, render);
    expect(out.title).toBe("Session started s-1");
    expect(out.summary).toBe("Reply");
  });
  it("render를 주지 않으면 옛 동작(tr만)", () => {
    const e = { uid: "u", title: "토큰" } as unknown as LogEvent;
    expect(localizeEvent(e, tr).title).toBe("Tokens");
  });
});
