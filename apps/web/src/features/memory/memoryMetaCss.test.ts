import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";

// 5.7R.37: 정보 영역 높이 상한 규칙 단언(레이아웃 API 없는 환경이라 CSS 규칙을 읽는다).
const css = readFileSync(join(import.meta.dirname, "memory.css"), "utf8");
const rule = (selector: string): string => {
  const m = css.match(new RegExp(`^${selector.replace(/[.]/g, "\\.")}\\s*\\{([^}]*)\\}`, "m"));
  if (m === null) throw new Error(`규칙 없음: ${selector}`);
  return m[1] ?? "";
};

describe("memory.css 정보 영역(screen-memory §5.2)", () => {
  const meta = rule(".mem-meta-scroll");
  const detail = rule(".mem-detail");

  it("상한은 상세 칸 높이에서 예약(머리+편집기 최소+상태 줄)을 뺀 값이라 내용 높이보다 낮은 고정 비율이 아니다", () => {
    expect(meta).toMatch(/max-height:\s*max\(160px,\s*calc\(100cqh - var\(--mem-meta-reserve\)\)\)/);
    expect(meta).not.toMatch(/45cqh/);
  });

  it("예약 값은 편집기 최소 높이(200)·머리(48)·상태 줄(28) 이상이다", () => {
    const reserve = Number(/--mem-meta-reserve:\s*(\d+)px/.exec(detail)?.[1]);
    expect(reserve).toBeGreaterThanOrEqual(48 + 200 + 28);
    expect(css).toMatch(/\.mem-detail-editor\s*\{[^}]*min-height:\s*200px/);
  });

  it("스크롤 단서는 유지한다(상시 스크롤바 자리, 하단 그림자는 공간을 차지하지 않음)", () => {
    expect(meta).toMatch(/overflow-y:\s*scroll/);
    expect(meta).toMatch(/scrollbar-gutter:\s*stable/);
    expect(rule(".mem-scroll-cue")).toMatch(/position:\s*sticky/);
  });
});
