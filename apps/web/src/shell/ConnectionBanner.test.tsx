import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { WsClient } from "@agent-console/api-client";
import { CONNECTION_BANNER_TIMING as T, useConnectionBanner } from "../app/connectionBanner";
import { createFakeWs } from "../testing/fakes";
import { ConnectionBanner } from "./ConnectionBanner";

function Probe({ ws, onReload }: { ws: WsClient; onReload: () => void }) {
  const b = useConnectionBanner(ws, { onReload });
  return <ConnectionBanner view={b.view} onRetry={b.retry} onReload={b.reload} />;
}

describe("ConnectionBanner", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });
  const setup = (initial: Parameters<typeof createFakeWs>[0] = "open") => {
    const ws = createFakeWs(initial);
    const onReload = vi.fn();
    render(<Probe ws={ws as unknown as WsClient} onReload={onReload} />);
    return { ws, onReload };
  };
  const adv = (ms: number) => act(() => void vi.advanceTimersByTime(ms));
  const set = (ws: ReturnType<typeof createFakeWs>, s: Parameters<typeof ws.setStatus>[0]) => act(() => ws.setStatus(s));

  it("정상(open)이면 아무것도 그리지 않는다", () => {
    setup();
    expect(document.querySelector(".app-conn-banner")).toBeNull();
  });

  it("reconnecting은 유예 안에 복구되면 한 번도 띄우지 않고, 넘으면 띄운다", () => {
    const { ws } = setup();
    set(ws, "reconnecting");
    adv(T.graceMs - 100);
    set(ws, "open");
    adv(5000);
    expect(document.querySelector(".app-conn-banner")).toBeNull();
    set(ws, "reconnecting");
    adv(T.graceMs - 100);
    set(ws, "connecting"); // 전환해도 타이머는 이어진다
    expect(document.querySelector(".app-conn-banner")).toBeNull();
    adv(200);
    expect(screen.getByText(/앱 서버/)).toBeTruthy();
    set(ws, "open");
    expect(screen.getByText("다시 연결되었습니다.")).toBeTruthy();
    adv(T.recoveredMs + 10);
    expect(document.querySelector(".app-conn-banner")).toBeNull();
  });

  it("첫 접속은 8초 뒤에 띄운다", () => {
    setup("connecting");
    adv(T.firstMs - 100);
    expect(document.querySelector(".app-conn-banner")).toBeNull();
    adv(200);
    expect(screen.getByText("앱 서버에 연결하는 중입니다…")).toBeTruthy();
  });

  it("closed는 즉시 [다시 연결]을 보이고, 2회 실패하면 [새로고침]도 보인다", () => {
    const { ws, onReload } = setup();
    set(ws, "closed");
    expect(screen.getByRole("alert")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "새로고침" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "다시 연결" }));
    expect(ws.connect).toHaveBeenCalledTimes(1);
    set(ws, "connecting");
    expect(screen.getByRole("button", { name: "연결하는 중…" }).hasAttribute("disabled")).toBe(true);
    set(ws, "closed");
    fireEvent.click(screen.getByRole("button", { name: "새로고침" }));
    expect(onReload).toHaveBeenCalled();
  });
});
