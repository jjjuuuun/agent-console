import { render } from "@testing-library/react";
import { useRef } from "react";
import { expect, test } from "vitest";

import { useVirtualRows } from "../src";

function List({ count, keepIndex }: { count: number; keepIndex?: number | null }) {
  const ref = useRef<HTMLDivElement>(null);
  const v = useVirtualRows({ count, rowHeight: 20, scrollRef: ref, fallbackHeight: 100, overscan: 1, ...(keepIndex !== undefined ? { keepIndex } : {}) });
  return (
    <div ref={ref} data-testid="list">
      {v.getVirtualItems().map((i) => (
        <div key={i.key} data-row={i.index} />
      ))}
    </div>
  );
}

const rows = (el: HTMLElement): number[] => [...el.querySelectorAll("[data-row]")].map((n) => Number(n.getAttribute("data-row")));

test("뷰포트를 읽을 수 없으면 fallbackHeight 분량(+overscan)만 그린다", () => {
  const { getByTestId } = render(<List count={1000} />);
  const r = rows(getByTestId("list"));
  expect(r[0]).toBe(0);
  expect(r.length).toBeLessThan(10);
  expect(r.length).toBeGreaterThanOrEqual(5);
});

test("keepIndex 행은 화면 밖이어도 그린다", () => {
  const { getByTestId } = render(<List count={1000} keepIndex={500} />);
  expect(rows(getByTestId("list"))).toContain(500);
});
