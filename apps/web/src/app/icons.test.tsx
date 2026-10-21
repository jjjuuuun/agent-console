import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { appIcons } from "./icons";

const markup = (name: string) => renderToStaticMarkup(createElement(appIcons[name]!, {}));

describe("아이콘 레지스트리", () => {
  it("서로 다른 이름은 같은 모양(SVG 문자열)을 갖지 않는다", () => {
    const seen = new Map<string, string>();
    for (const name of Object.keys(appIcons)) {
      const m = markup(name);
      const prev = seen.get(m);
      expect(prev, `${name} 은(는) ${prev} 와 같은 모양`).toBeUndefined();
      seen.set(m, name);
    }
  });

  it("설정은 방사형 짧은 선분(해 모양) 없이 닫힌 톱니 외곽선 + 원이다", () => {
    const m = markup("settings");
    const d = [...m.matchAll(/ d="([^"]+)"/g)].map((x) => x[1] ?? "");
    expect(d.length).toBeGreaterThan(0);
    for (const path of d) {
      expect(path).not.toMatch(/[vhVH]\s*-?\d/); // 수직·수평 선분 명령 없음
      expect(path).toMatch(/z$/i); // 열린 선 없음
    }
    expect(m).toContain("<circle");
  });

  it("테마 도구줄용 고정 아이콘 theme이 있고 해·달·모니터와 모양이 다르다", () => {
    expect(appIcons.theme).toBeDefined();
    for (const other of ["theme-light", "theme-dark", "theme-system", "settings"]) expect(markup("theme")).not.toBe(markup(other));
  });
});
