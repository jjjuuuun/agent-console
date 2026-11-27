import { describe, expect, it } from "vitest";
import type { UsageSourceInfo } from "@agent-console/contracts";
import { translateUsageSources } from "./usageLib";

const info: UsageSourceInfo = {
  enabled: true,
  descriptor: {
    id: "src-a",
    title: "원문 제목",
    trust: "official",
    description: "원문 설명",
    setup_help: "원문 안내",
    windows: [{ id: "five_hour", title: "5시간", short_title: "5h" }],
    setup_snippets: [{ title: "조각", shell: "bash", language: "bash", text: "echo hi" }],
  },
} as UsageSourceInfo;

describe("translateUsageSources", () => {
  const table: Record<string, string> = { "원문 제목": "Title", "원문 설명": "Desc", "원문 안내": "Help", "5시간": "5 hours", "조각": "Snippet" };
  const tr = (s: string) => table[s] ?? s;

  it("보이는 서버 원문만 바꾸고 id·신뢰 등급·조각 본문은 그대로 둔다", () => {
    const [out] = translateUsageSources([info], tr);
    const d = out!.descriptor;
    expect(d.title).toBe("Title");
    expect(d.description).toBe("Desc");
    expect(d.setup_help).toBe("Help");
    expect(d.windows?.[0]).toMatchObject({ id: "five_hour", title: "5 hours", short_title: "5h" });
    expect(d.setup_snippets?.[0]).toMatchObject({ title: "Snippet", text: "echo hi" });
    expect(d.id).toBe("src-a");
    expect(d.trust).toBe("official");
  });

  it("모르는 문구는 원문 그대로이고 원본은 바뀌지 않는다", () => {
    const [out] = translateUsageSources([info], (s) => s);
    expect(out!.descriptor.title).toBe("원문 제목");
    expect(translateUsageSources([info], tr)[0]).not.toBe(info);
    expect(info.descriptor.title).toBe("원문 제목");
  });
});
