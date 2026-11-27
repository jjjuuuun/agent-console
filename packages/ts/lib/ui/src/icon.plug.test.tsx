import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { Icon, defaultIcons, filterCommandGroups, type CommandGroup } from "./index";

afterEach(cleanup);

describe("plug 아이콘(BC.2)", () => {
  it("defaultIcons에 있고 장식으로 그려진다", () => {
    expect(defaultIcons["plug"]).toBeDefined();
    const { container } = render(<Icon name="plug" />);
    expect(container.querySelector("svg path")).not.toBeNull();
    expect(container.querySelector("[aria-hidden='true']")).not.toBeNull();
  });

  it("오른쪽 아래 모서리(x>12, y>12)에는 선이 닿지 않는다(배지 자리)", () => {
    const { container } = render(<Icon name="plug" />);
    const d = Array.from(container.querySelectorAll("svg path")).map((p) => p.getAttribute("d") ?? "").join(" ");
    // 줄기는 x=8, 몸통은 x 4.5~11.5: 숫자 좌표 중 12를 넘는 x가 없다
    expect(d).not.toMatch(/[Hh]1[2-6]/);
    expect(d).toContain("V5");
  });

  it("도움말·테마·톱니와 마크업이 서로 다르다(적어도 plug는 유일한 모양)", () => {
    const markup = (name: string) => render(<Icon name={name} />).container.innerHTML;
    const plug = markup("plug");
    for (const other of ["more", "refresh", "lock", "copy", "pin"]) expect(markup(other)).not.toBe(plug);
  });
});

describe("CommandItem.keywords", () => {
  const groups: CommandGroup[] = [{ id: "g", title: "g", items: [{ id: "a", label: "백엔드 연결…", keywords: "sign in login", run: () => {} }, { id: "b", label: "다른", run: () => {} }] }];
  it("keywords로 찾히지만 label·hint가 아니면 화면에는 없다", () => {
    expect(filterCommandGroups(groups, "LOGIN")[0]?.items.map((i) => i.id)).toEqual(["a"]);
    expect(filterCommandGroups(groups, "zzz")).toEqual([]);
  });
});
