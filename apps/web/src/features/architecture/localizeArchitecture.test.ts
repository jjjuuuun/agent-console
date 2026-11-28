import { describe, expect, it } from "vitest";
import type { ArchitectureView } from "@agent-console/contracts";
import { localizeArchitectureProfiles, localizeArchitectureView } from "./localizeArchitecture";

const tr = (text: string): string => (text === "입력" ? "Input" : text);

describe("localizeArchitectureView", () => {
  it("서버 글자(칸 제목·설명·그룹·연결 라벨·비고)를 옮기고 아이디·지표는 그대로 둔다", () => {
    const view = {
      profile: "p",
      title: "입력",
      zones: [{ id: "z", label: "입력", x: 0, y: 0, w: 1, h: 1 }],
      cells: [{ id: "입력", label: "입력", description: "입력", w: 1, h: 1, status: "observed", selector: {}, groups: [{ key: "k", label: "입력", selector: {} }] }],
      edges: [{ id: "e", from: "a", to: "b", label: "입력", kind: "observed", status: "observed" }],
      notes: [{ code: "c", message: "입력" }],
      event_total: 3,
    } as unknown as ArchitectureView;
    const out = localizeArchitectureView(view, tr);
    expect(out.title).toBe("Input");
    expect(out.zones?.[0]?.label).toBe("Input");
    expect(out.cells?.[0]).toMatchObject({ id: "입력", label: "Input", description: "Input" });
    expect(out.cells?.[0]?.groups?.[0]?.label).toBe("Input");
    expect(out.edges?.[0]?.label).toBe("Input");
    expect(out.notes?.[0]?.message).toBe("Input");
    expect(out.event_total).toBe(3);
  });

  it("프로필 이름을 옮긴다", () => {
    const out = localizeArchitectureProfiles({ profiles: [{ id: "a", title: "입력", origin: "default" }, { id: "b", origin: "user" }] }, tr);
    expect(out.profiles?.[0]?.title).toBe("Input");
    expect(out.profiles?.[1]?.title).toBeUndefined();
  });
});
