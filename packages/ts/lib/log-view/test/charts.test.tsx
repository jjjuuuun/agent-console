import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { builtinWidgets, createWidgetRegistry, DashboardGrid } from "../src";
import { slotFor, widget } from "./fixtures";

// 차트 라이브러리 로드가 실패하는 환경: 위젯은 표로 대체되고 안내가 보인다(F-12, 로드 실패 폴백).
vi.mock("../src/charts/RechartsLine", () => ({
  default: () => {
    throw new Error("chunk load failed");
  },
}));

afterEach(cleanup);

it("차트가 로드·렌더에 실패하면 표로 대체하고 안내한다", async () => {
  const spy = vi.spyOn(console, "error").mockImplementation(() => undefined);
  try {
    const w = widget("ln", "line", { query: { group_by: ["dim-t"], metric: "m" } });
    render(
      <DashboardGrid
        widgets={[w]}
        registry={createWidgetRegistry(builtinWidgets)}
        results={{ ln: { loading: false, rows: [{ keys: { "dim-t": "d1" }, value: 4 }] } }}
        slotFor={slotFor}
      />,
    );
    await waitFor(() => expect(screen.getByText("차트를 불러오지 못해 표로 보여줍니다")).toBeTruthy());
    expect(screen.getByRole("table")).toBeTruthy();
    expect(screen.getByText("d1")).toBeTruthy();
  } finally {
    spy.mockRestore();
  }
});
