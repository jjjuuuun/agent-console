import { describe, expect, it } from "vitest";
import type { Issue } from "@agent-console/contracts";
import { buildIssueRows, rowSuggestions } from "./issueRows";

const mk = (over: Partial<Issue>): Issue => ({ severity: "info", code: "zz.any", message: "m", ...over }) as Issue;

describe("buildIssueRows (5.7R.38)", () => {
  it("임의 코드·group.key 이슈를 한 행으로 묶고 group이 없으면 그대로 둔다", () => {
    const rows = buildIssueRows([
      mk({ node_id: "a", group: { key: "k1", message: "묶음" } }),
      mk({ severity: "error", code: "q", node_id: "x" }),
      mk({ node_id: "b", group: { key: "k1", message: "묶음" } }),
      mk({ node_id: "c", group: { key: "k1", message: "묶음" } }),
    ]);
    expect(rows.map((r) => [r.severity, r.issues.length])).toEqual([["error", 1], ["info", 3]]);
    expect(rows[1]!.groupMessage).toBe("묶음");
  });
  it("같은 id 제안은 하나로 합치고 개수를 센다", () => {
    const sug = (n: string) => ({ id: "unset", label: "값 비우기", patch: { unset_node_fields: [{ node_id: n, path: "/x" }] } });
    const rows = buildIssueRows([
      mk({ node_id: "a", group: { key: "k", message: "g" }, suggestions: [sug("a")] }),
      mk({ node_id: "b", group: { key: "k", message: "g" }, suggestions: [sug("b")] }),
    ]);
    const s = rowSuggestions(rows[0]!);
    expect(s).toHaveLength(1);
    expect(s[0]!.count).toBe(2);
    expect(s[0]!.suggestion.patch?.unset_node_fields).toHaveLength(2);
  });
});
