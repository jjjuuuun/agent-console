import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import en from "../locales/en.json";
import { NodeCard, NARROW_NODE_WIDTH } from "./NodeCard";

afterEach(cleanup);

const base = { label: "Build", typeTitle: "Agent", accent: "#888", iconText: "B", inputs: [], outputs: [], messages: en.messages };

describe("NodeCard 상태 라벨(I.14 B1·B2)", () => {
  it("좁은 칸에는 짧은 상태 단어를 쓰고 전체 단어는 title에 둔다", () => {
    const { container } = render(<NodeCard {...base} state={{ status: "succeeded" }} />);
    const status = container.querySelector(".ac-ge-status");
    expect(status?.textContent).toBe("Done");
    expect(status?.getAttribute("title")).toBe("Succeeded");
  });

  it("짧은 형이 없는 상태는 전체 라벨 그대로", () => {
    const { container } = render(<NodeCard {...base} state={{ status: "failed" }} />);
    expect(container.querySelector(".ac-ge-status")?.textContent).toBe("Failed");
  });

  it("폭이 기준보다 좁으면 data-narrow를 단다", () => {
    const { container } = render(<NodeCard {...base} width={NARROW_NODE_WIDTH - 1} />);
    expect(container.querySelector(".ac-ge-node")?.getAttribute("data-narrow")).toBe("true");
    cleanup();
    const wide = render(<NodeCard {...base} width={NARROW_NODE_WIDTH} />);
    expect(wide.container.querySelector(".ac-ge-node")?.hasAttribute("data-narrow")).toBe(false);
  });
});

describe("복수형(I.14)", () => {
  it("개수가 1이면 단수형 문구를 쓴다", async () => {
    const { formatCount } = await import("../messages");
    expect(formatCount(en.messages as never, "removed", 1, { count: 1 })).toBe("Deleted 1 item.");
    expect(formatCount(en.messages as never, "removed", 3, { count: 3 })).toBe("Deleted 3 items.");
  });
});
