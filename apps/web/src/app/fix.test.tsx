import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, describe, expect, it } from "vitest";
import type { FixAction } from "@agent-console/contracts";
import { FixButtons, fixActionTo } from "./fix";
import { ErrorBlock } from "./ErrorBlock";
import { DEFAULT_ROUTES } from "../shell/routeConfig";

afterEach(cleanup);

const settingsRole = DEFAULT_ROUTES.find((r) => r.id === "settings")?.serves ?? "";
const action = (role: string, extra: Partial<FixAction["target"]> = {}, focus?: string): FixAction => ({ label: "고치기", target: { role, ...extra }, ...(focus ? { focus } : {}) });

describe("fixActionTo", () => {
  it("역할을 라우트 설정에서 경로로 풀고 id·section·focus를 붙인다", () => {
    expect(fixActionTo(action(settingsRole, { section: "common" }, "/backend"))).toBe("/settings?section=common&focus=%2Fbackend");
    const graph = DEFAULT_ROUTES.find((r) => r.id === "teams");
    expect(fixActionTo(action(graph?.serves ?? "", { id: "g 1", section: "n1" }, "/backend"))).toBe("/teams/g%201?section=n1&focus=%2Fbackend");
  });
  it("위치·필드가 없는 해결은 항목 id가 있을 때 도착 표시(fix=1)를 붙인다", () => {
    const graph = DEFAULT_ROUTES.find((r) => r.id === "teams");
    expect(fixActionTo(action(graph?.serves ?? "", { id: "g1" }))).toBe("/teams/g1?fix=1");
    expect(fixActionTo(action(graph?.serves ?? ""))).toBe("/teams");
  });
  it("역할을 맡은 화면이 없으면 undefined", () => {
    expect(fixActionTo(action("no-such-role"))).toBeUndefined();
  });
});

function view(node: React.ReactNode) {
  const router = createMemoryRouter([{ path: "*", element: node }], { initialEntries: ["/x"] });
  render(<RouterProvider router={router} />);
  return router;
}

describe("FixButtons·ErrorBlock", () => {
  it("버튼을 누르면 그 화면으로 이동한다", async () => {
    const router = view(<ErrorBlock title="문제" message="설명" fix={{ actions: [action(settingsRole, { section: "common" }, "/backend")] }} />);
    fireEvent.click(await screen.findByRole("button", { name: "고치기" }));
    expect(router.state.location.pathname).toBe("/settings");
    expect(router.state.location.search).toBe("?section=common&focus=%2Fbackend");
  });
  it("역할을 맡은 화면이 없는 버튼은 숨기고, 버튼이 없으면 아무것도 그리지 않는다", async () => {
    view(
      <>
        <FixButtons fix={{ actions: [action("no-such-role")] }} />
        <FixButtons fix={null} />
        <p>끝</p>
      </>,
    );
    await screen.findByText("끝");
    expect(screen.queryByRole("button")).toBeNull();
  });
});
