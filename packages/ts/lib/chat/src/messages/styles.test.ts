import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const css = readFileSync(join(import.meta.dirname, "..", "styles.css"), "utf-8");

describe("styles.css (채팅 턴, 5.2R.21)", () => {
  it("내 메시지 말풍선: 오른쪽 정렬, 최대 폭, 우하단만 4px, accent-bg", () => {
    expect(css).toMatch(/\.ac-chat-me \{[^}]*align-self: flex-end[^}]*min\(70%, 560px\)/);
    expect(css).toMatch(/\.ac-chat-bubble \{[^}]*var\(--ac-accent-bg\)[^}]*4px var\(--ac-radius-lg\)/);
  });
  it("중간 결과는 점선 카드, 진행 행 들여쓰기는 --ac-depth × --ac-progress-indent 한 규칙", () => {
    expect(css).toMatch(/\[data-intermediate="true"\][^{]*\{[^}]*1px dashed/);
    expect(css).toMatch(/\.ac-chat-row \{[^}]*calc\(var\(--ac-depth\) \* var\(--ac-progress-indent/);
  });
  it("호버 보조 줄은 포커스-within과 터치(hover: none)에서도 보인다", () => {
    expect(css).toContain(":focus-within .ac-chat-me-meta");
    expect(css).toContain("@media (hover: none)");
  });
  it("색은 토큰만 쓴다(16진 색 없음)", () => {
    expect(css.slice(css.indexOf("5.2R.21"))).not.toMatch(/#[0-9a-fA-F]{3,8}\b/);
  });
});
