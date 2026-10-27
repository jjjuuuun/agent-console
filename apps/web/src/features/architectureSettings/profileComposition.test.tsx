import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ProfileEditor } from "./ProfileEditor";

// 관심사는 조합 상태 연결이다. 실제 CodeMirror 대신 같은 props(onChange·onCompositionChange)를 쓰는 textarea로 바꾼다.
vi.mock("../library", async (orig) => ({
  ...(await orig<object>()),
  LazyTextEditor: (p: { value: string; ariaLabel: string; onChange?: (v: string) => void; onCompositionChange?: (c: boolean) => void }) => (
    <textarea
      aria-label={p.ariaLabel}
      value={p.value}
      onChange={(e) => p.onChange?.(e.target.value)}
      onCompositionStart={() => p.onCompositionChange?.(true)}
      onCompositionEnd={() => p.onCompositionChange?.(false)}
    />
  ),
}));

afterEach(cleanup);
const LONG = { timeout: 15_000 };
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

describe("ProfileEditor: IME 조합 중 검사 보류", () => {
  it("조합 중에는 서버 검사를 부르지 않고, 조합이 끝나면 1회 부른다", async () => {
    const check = vi.fn(async () => ({ issues: [] }));
    render(<ProfileEditor id="p1" title="t" initialText={"title: 가\n"} readOnly={false} check={check} onSave={() => undefined} onClose={() => undefined} delayMs={30} />);
    await waitFor(() => expect(check).toHaveBeenCalledTimes(1), LONG);
    const box = screen.getByRole("textbox", { name: "프로필 YAML" });
    fireEvent.compositionStart(box);
    fireEvent.change(box, { target: { value: "title: 가ㅎ\n" } });
    fireEvent.change(box, { target: { value: "title: 가한\n" } });
    await sleep(150);
    expect(check).toHaveBeenCalledTimes(1);
    fireEvent.compositionEnd(box);
    await waitFor(() => expect(check).toHaveBeenCalledTimes(2), LONG);
    expect(check).toHaveBeenLastCalledWith({ id: "p1", profile: { title: "가한" } });
  });
});
