import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { lazyScreen } from "./lazyScreen";

afterEach(cleanup);

describe("lazyScreen 오류 경계", () => {
  it("불러오기에 실패하면 안내와 [다시 시도]를 보이고, 다시 시도하면 화면이 열린다", async () => {
    let fail = true;
    const Screen = lazyScreen(async () => {
      if (fail) throw new Error("Failed to fetch dynamically imported module");
      return { Page: () => <p>열린 화면</p> };
    }, "Page");
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    render(<div><nav>셸</nav><Screen /></div>);
    expect(await screen.findByText("화면을 불러오지 못했습니다")).toBeTruthy();
    expect(screen.getByText("셸")).toBeTruthy();
    expect(screen.getByRole("button", { name: "새로 고침" })).toBeTruthy();
    fail = false;
    fireEvent.click(screen.getByRole("button", { name: "다시 시도" }));
    await waitFor(() => expect(screen.getByText("열린 화면")).toBeTruthy());
  });

  it("화면 렌더 중 예외가 나도 셸은 유지되고 오류 안내가 보인다", async () => {
    const Screen = lazyScreen(async () => ({ Page: (): never => { throw new Error("boom"); } }), "Page");
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    render(<div><nav>셸</nav><Screen /></div>);
    expect(await screen.findByText("이 화면에서 오류가 났습니다")).toBeTruthy();
    expect(screen.getByText("셸")).toBeTruthy();
  });
});
