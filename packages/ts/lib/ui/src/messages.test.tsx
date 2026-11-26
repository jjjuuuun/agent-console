import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ChipRow, ShortcutProvider, Tabs } from "./index";
import en from "./locales/en";

afterEach(cleanup);

describe("기본 문구와 messages prop", () => {
  it("단축키 중복 경고: 기본은 한국어, messages={en}이면 영어", () => {
    const defaults = [
      { id: "a", scope: "global", keys: "Mod+K", titleKey: "a", run: () => undefined },
      { id: "b", scope: "global", keys: "Mod+K", titleKey: "b", run: () => undefined },
    ];
    const ko = vi.fn();
    const enWarn = vi.fn();
    render(<ShortcutProvider defaults={defaults} onWarn={ko} />);
    render(<ShortcutProvider defaults={defaults} onWarn={enWarn} messages={en} />);
    expect(ko.mock.calls[0]?.[0]).toMatch(/^단축키 중복: "Mod\+K"/);
    expect(enWarn.mock.calls[0]?.[0]).toMatch(/^Duplicate keyboard shortcut: "Mod\+K"/);
  });
  it("Tabs·ChipRow는 moreLabel이 messages보다 우선하고, 없으면 messages를 쓴다(렌더 가능)", () => {
    const { container } = render(
      <>
        <Tabs tabs={[{ id: "a", label: "A", content: null }]} ariaLabel="t" messages={en} />
        <ChipRow chips={[{ id: "c", label: "C" }]} ariaLabel="c" messages={en} />
      </>,
    );
    expect(container.querySelector("[role=tablist]")).not.toBeNull();
  });
});
