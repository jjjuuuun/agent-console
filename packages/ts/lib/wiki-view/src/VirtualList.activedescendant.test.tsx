import { cleanup, render } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it } from "vitest";
import { VirtualList } from "./VirtualList";

afterEach(cleanup);
beforeAll(() => {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
});

const items = Array.from({ length: 2000 }, (_, i) => `행 ${i}`);

function List({ activeIndex }: { activeIndex: number }) {
  return (
    <VirtualList
      items={items}
      rowHeight={28}
      height={200}
      role="listbox"
      ariaLabel="목록"
      tabIndex={0}
      activeIndex={activeIndex}
      activeDescendant={`row-${activeIndex}`}
      getKey={(_, i) => String(i)}
      renderRow={(item, ctx) => <div id={`row-${ctx.index}`} role="option" aria-selected={false} style={ctx.style}>{item}</div>}
    />
  );
}

describe("VirtualList aria-activedescendant", () => {
  it("활성 행이 DOM에 있으면 가리키고, 가상화로 그려지지 않으면 속성을 뺀다(가리키는 id가 항상 DOM에 있다)", () => {
    const { container } = render(<List activeIndex={1} />);
    const box = container.querySelector<HTMLElement>("[role=listbox]")!;
    expect(box.getAttribute("aria-activedescendant")).toBe("row-1");
    expect(container.querySelector("#row-1")).not.toBeNull();
    const hidden = render(<List activeIndex={1500} />);
    const box2 = hidden.container.querySelector<HTMLElement>("[role=listbox]")!;
    const id = box2.getAttribute("aria-activedescendant");
    if (id !== null) expect(hidden.container.querySelector(`#${id}`)).not.toBeNull();
  });
});
