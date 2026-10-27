import { describe, expect, it } from "vitest";
import { focusLogControl } from "./focus";

function mount(html: string): HTMLElement {
  const host = document.createElement("div");
  host.innerHTML = html;
  document.body.appendChild(host);
  return host;
}

describe("focusLogControl", () => {
  it("대상 단추로 포커스를 옮기고 찾았음을 알린다", () => {
    const host = mount('<div class="ac-lv-filterbar"><button id="f">필터</button></div><div class="ac-lv-catchips"><button id="c">칩</button></div>');
    expect(focusLogControl("filterBar", { root: host })).toBe(true);
    expect(document.activeElement?.id).toBe("f");
    expect(focusLogControl("categoryChips", { root: host })).toBe(true);
    expect(document.activeElement?.id).toBe("c");
    host.remove();
  });
  it("activate면 누르고, 대상이 없으면 false", () => {
    const host = mount('<div class="ac-lv-addwrap"><button id="a">추가</button></div>');
    let clicks = 0;
    host.querySelector("#a")?.addEventListener("click", () => clicks++);
    expect(focusLogControl("addFilter", { root: host, activate: true })).toBe(true);
    expect(clicks).toBe(1);
    expect(focusLogControl("categoryChips", { root: host })).toBe(false);
    host.remove();
  });
});
