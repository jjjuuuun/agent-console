import { readFileSync } from "node:fs";
import { join } from "node:path";
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { Icon, defaultIcons } from "./index";

afterEach(cleanup);

describe("구조도 아이콘(5.5R.15)", () => {
  it("defaultIcons.architecture는 3×3 격자(칸 9개)이고 장식으로 그려진다", () => {
    expect(defaultIcons["architecture"]).toBeDefined();
    const { container } = render(<Icon name="architecture" size={32} />);
    const path = container.querySelector("svg path")?.getAttribute("d") ?? "";
    expect(path.match(/z/gi)).toHaveLength(9);
    expect(container.querySelector("[aria-hidden='true']")).not.toBeNull();
    expect(container.querySelector("svg")?.getAttribute("width")).toBe("32");
  });

  it("tokens.css에 --ac-icon-architecture 마스크 토큰이 있고 같은 9칸 모양이다", () => {
    const css = readFileSync(join(import.meta.dirname, "tokens.css"), "utf-8");
    const m = /--ac-icon-architecture: url\("data:image\/svg\+xml,([^"]+)"\)/.exec(css);
    expect(m).not.toBeNull();
    expect(decodeURIComponent(m![1]!).match(/z/gi)).toHaveLength(9);
  });
});
