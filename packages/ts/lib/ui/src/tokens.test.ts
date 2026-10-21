import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

/** tokens.css를 텍스트로 파싱해 약속(변수·유틸 클래스·상태 규칙)이 지켜지는지 검사한다. 다른 패키지가 이 토큰을 쓰는지는 저장소 수준 검사(apps/web/src/app/tokenConsumers.test.ts)가 본다. */
const here = import.meta.dirname;
const css = readFileSync(join(here, "tokens.css"), "utf-8");

/** 블록 본문: 선택자 문자열이 정확히 일치하는 첫 규칙의 { ... } 안. 중첩 @media는 지원하지 않는다. */
function ruleBody(selector: string, source = css): string {
  const esc = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const m = new RegExp(`(?:^|\\})\\s*${esc}\\s*\\{([^}]*)\\}`, "m").exec(source);
  if (!m) throw new Error(`규칙 없음: ${selector}`);
  return m[1]!;
}
const declared = (body: string) => new Set([...body.matchAll(/(--ac-[a-z0-9-]+)\s*:/g)].map((m) => m[1]!));

const darkBlock = ruleBody(':root,\n:root[data-theme="dark"]');
const lightBlock = ruleBody(':root[data-theme="light"]');
const systemMatch = /@media \(prefers-color-scheme: light\)\s*\{\s*:root:not\(\[data-theme\]\)\s*\{([^}]*)\}/.exec(css);
const allDefined = declared(css);

describe("테마", () => {
  it("다크 기본 / 라이트 / 시스템(속성 없음 + 라이트 선호)이 같은 이름을 정의한다", () => {
    expect(systemMatch).not.toBeNull();
    const dark = declared(darkBlock);
    const light = declared(lightBlock);
    expect([...dark].sort()).toEqual([...light].sort());
    expect([...declared(systemMatch![1]!)].sort()).toEqual([...light].sort());
    expect(dark.size).toBeGreaterThanOrEqual(40);
  });
  it("tokens.md의 대표 색 값", () => {
    expect(darkBlock).toContain("--ac-bg: #14161d");
    expect(lightBlock).toContain("--ac-bg: #f5f4f0");
    expect(darkBlock).toContain("--ac-accent: #8ea2ff");
    expect(lightBlock).toContain("--ac-accent: #4651d6");
  });
  it("한글 폰트 스택과 fallback", () => {
    expect(css).toMatch(/--ac-font-sans:\s*'Pretendard', 'Noto Sans KR', 'Malgun Gothic', 'Apple SD Gothic Neo', system-ui, sans-serif/);
    expect(css).toMatch(/--ac-font-mono:[^;]*'D2Coding'[^;]*'Malgun Gothic'/);
  });
  it("글자 크기 토큰은 12px 이상", () => {
    for (const m of css.matchAll(/--ac-text-(xs|sm|md|lg|xl|code):\s*([\d.]+)px/g)) expect(Number(m[2])).toBeGreaterThanOrEqual(12);
  });
  it("간격·반경·컨트롤 토큰", () => {
    for (const n of ["space-0", "space-1", "space-2", "space-3", "space-4", "space-5", "space-6", "space-7", "radius-sm", "radius-md", "radius-lg", "radius-full", "control-sm", "control-md", "control-lg", "dur-fast", "dur-base", "ease"]) {
      expect(allDefined.has(`--ac-${n}`), n).toBe(true);
    }
  });
});

describe("분류색·상태 토큰", () => {
  it("분류색 --ac-cat-1..8 과 neutral, 상태 색·bg 토큰", () => {
    for (let i = 1; i <= 8; i++) expect(allDefined.has(`--ac-cat-${i}`)).toBe(true);
    expect(allDefined.has("--ac-cat-neutral")).toBe(true);
    for (const s of STATES) {
      expect(declared(darkBlock).has(`--ac-status-${s}`), s).toBe(true);
      expect(allDefined.has(`--ac-status-${s}-bg`), s).toBe(true);
    }
  });
});

describe("유틸 클래스", () => {
  it.each(["ac-text", "ac-ellipsis", "ac-clamp-2", "ac-clamp-3", "ac-mono-wrap", "ac-pre", "ac-status-icon"])(".%s 정의", (cls) => {
    expect(css).toMatch(new RegExp(`\\.${cls}[\\s,{:\\[]`));
  });
  it("넘침 규칙의 핵심 선언", () => {
    expect(ruleBody(".ac-ellipsis")).toMatch(/white-space:\s*nowrap[^]*overflow:\s*hidden[^]*text-overflow:\s*ellipsis[^]*min-width:\s*0/);
    expect(ruleBody(".ac-text")).toMatch(/word-break:\s*keep-all[^]*overflow-wrap:\s*break-word/);
    expect(ruleBody(".ac-mono-wrap")).toMatch(/word-break:\s*break-all[^]*overflow-wrap:\s*anywhere/);
    for (const sel of [".ac-clamp-2, .ac-clamp-3", ".ac-pre"]) expect(ruleBody(sel), sel).toMatch(/word-break:\s*keep-all[^]*overflow-wrap:\s*(break-word|anywhere)/);
    expect(css).toContain("-webkit-line-clamp: 2");
    expect(css).toContain("-webkit-line-clamp: 3");
  });
});

const STATES = ["pending", "queued", "running", "succeeded", "failed", "skipped", "waiting", "cancelled"] as const;
const COLORS: Record<(typeof STATES)[number], [string, string]> = {
  pending: ["#8b94a3", "#667085"], queued: ["#7aa2d6", "#3b6ea5"], running: ["#35c2d6", "#0e7c8c"], succeeded: ["#3fb871", "#1a7f4b"],
  failed: ["#f26b6b", "#c4302b"], skipped: ["#7b8494", "#6b7280"], waiting: ["#f0b429", "#9a6700"], cancelled: ["#a78bfa", "#6d4fc2"],
};

describe("노드 상태 8종 [data-status]", () => {
  for (const s of STATES) {
    it(`${s}: 색 토큰(다크/라이트), 규칙(색·테두리·아이콘)`, () => {
      expect(darkBlock).toContain(`--ac-status-${s}: ${COLORS[s][0]}`);
      expect(lightBlock).toContain(`--ac-status-${s}: ${COLORS[s][1]}`);
      const body = ruleBody(`[data-status="${s}"]`);
      for (const v of ["--ac-status:", "--ac-status-bg:", "--ac-status-border-style:", "--ac-status-border-width:", "--ac-status-icon:"]) expect(body, v).toContain(v);
      expect(body).toContain(`var(--ac-icon-${s})`);
      expect(css).toMatch(new RegExp(`--ac-icon-${s}: url\\("data:image/svg\\+xml,`));
    });
  }
  it("테두리 패턴이 상태마다 구분된다(점선 종류·두께)", () => {
    expect(ruleBody('[data-status="pending"]')).toContain("border-style: dashed");
    expect(ruleBody('[data-status="queued"]')).toContain("border-style: dotted");
    expect(ruleBody('[data-status="running"]')).toContain("border-width: 2px");
    expect(ruleBody('[data-status="failed"]')).toContain("border-width: 2px");
    expect(ruleBody('[data-status="skipped"]')).toContain("border-style: dashed");
  });
  it("running 진행 막대·스피너, waiting 깜박임, skipped 빗금·불투명도 .7, waiting 바깥 링", () => {
    expect(css).toContain("@keyframes ac-spin");
    expect(css).toContain("@keyframes ac-blink");
    expect(css).toContain("@keyframes ac-progress");
    expect(css).toMatch(/\[data-status="skipped"\][^{]*\{\s*background-image:\s*repeating-linear-gradient\(45deg/);
    expect(css).toMatch(/opacity:\s*0\.7/);
    expect(css).toMatch(/\[data-status="waiting"\]:not\(:focus-visible\)[^{]*\{\s*outline:\s*1\.5px solid[^}]*outline-offset:\s*2px/);
  });
  it("prefers-reduced-motion: 전역 애니메이션 정지 + running 막대는 정지 줄무늬", () => {
    const blocks = css.split("@media (prefers-reduced-motion: reduce)").slice(1);
    expect(blocks.length).toBeGreaterThanOrEqual(2);
    expect(blocks.join("\n")).toContain("animation-duration: 0.01ms");
    expect(blocks.join("\n")).toMatch(/\.ac-status-icon[^{]*\{\s*animation:\s*none/);
    expect(blocks.join("\n")).toMatch(/running[^{]*::after\s*\{\s*animation:\s*none;\s*background:\s*repeating-linear-gradient\(90deg/);
  });
  it("모르는 상태 폴백: 8종 + Run 확장을 제외한 모든 값 = 점선 + 물음표", () => {
    const m = /(\[data-status\]:not\([^{]*)\{([^}]*)\}/.exec(css);
    expect(m).not.toBeNull();
    for (const s of STATES) expect(m![1]).toContain(`[data-status="${s}"]`);
    for (const s of ["completed", "paused", "interrupted"]) expect(m![1]).toContain(`[data-status="${s}"]`);
    expect(m![2]).toContain("border-style: dashed");
    expect(m![2]).toContain("var(--ac-icon-unknown)");
    expect(css).toMatch(/--ac-icon-unknown: url\(/);
  });
});

describe("Run 상태 [data-status-kind=run]", () => {
  it("completed는 succeeded, paused는 waiting(깜박임 없음), interrupted는 failed 색 + 점선 + 번개", () => {
    expect(ruleBody('[data-status-kind="run"][data-status="completed"]')).toContain("var(--ac-status-succeeded)");
    const paused = ruleBody('[data-status-kind="run"][data-status="paused"]');
    expect(paused).toContain("var(--ac-status-waiting)");
    expect(css).toMatch(/\[data-status="waiting"\]:not\(\[data-status-kind="run"\]\) \.ac-status-icon/); // 깜박임은 node waiting 에만
    const interrupted = ruleBody('[data-status-kind="run"][data-status="interrupted"]');
    expect(interrupted).toContain("var(--ac-status-failed)");
    expect(interrupted).toContain("border-style: dashed");
    expect(interrupted).toContain("var(--ac-icon-interrupted)");
  });
});

function lum(hex: string): number {
  const c = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
  return 0.2126 * c[0]! + 0.7152 * c[1]! + 0.0722 * c[2]!;
}
const contrast = (a: string, b: string) => {
  const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x);
  return (hi! + 0.05) / (lo! + 0.05);
};
const val = (block: string, name: string) => new RegExp(`${name}:\\s*(#[0-9a-fA-F]{6})`).exec(block)![1]!;

describe("대비 기준 (tokens.md: 본문 4.5:1, 경계·아이콘 3:1)", () => {
  for (const [theme, block] of [["다크", darkBlock], ["라이트", lightBlock]] as const) {
    const surfaces = ["--ac-bg", "--ac-surface-1", "--ac-surface-2", "--ac-surface-3"];
    it(`${theme}: 본문·보조·힌트 텍스트 4.5 이상`, () => {
      for (const t of ["--ac-text", "--ac-text-muted", "--ac-text-subtle"]) {
        for (const s of surfaces) expect(contrast(val(block, t), val(block, s)), `${t} on ${s}`).toBeGreaterThanOrEqual(4.5);
      }
    });
    it(`${theme}: border-strong 은 모든 표면에서 3 이상`, () => {
      for (const s of surfaces) expect(contrast(val(block, "--ac-border-strong"), val(block, s)), s).toBeGreaterThanOrEqual(3);
    });
    it(`${theme}: 상태 색은 surface-1/2 에서 3 이상`, () => {
      for (const st of STATES) {
        for (const s of ["--ac-surface-1", "--ac-surface-2"]) expect(contrast(val(block, `--ac-status-${st}`), val(block, s)), `${st} on ${s}`).toBeGreaterThanOrEqual(3);
      }
    });
  }
});

/** color-mix(in srgb, fg pct%, bg) 의 결과 색(16진). */
function mix(fg: string, bg: string, pct: number): string {
  const c = [1, 3, 5].map((i) => Math.round((parseInt(fg.slice(i, i + 2), 16) * pct + parseInt(bg.slice(i, i + 2), 16) * (100 - pct)) / 100));
  return `#${c.map((v) => v.toString(16).padStart(2, "0")).join("")}`;
}

describe("채팅 턴 대비 쌍 (5.2R.21, ux-overhaul §13-1)", () => {
  for (const [theme, block] of [["다크", darkBlock], ["라이트", lightBlock]] as const) {
    it(`${theme}: 내 말풍선 글자(--ac-text on --ac-accent-bg = accent 16% + surface-1) 4.5 이상`, () => {
      expect(contrast(val(block, "--ac-text"), mix(val(block, "--ac-accent"), val(block, "--ac-surface-1"), 16))).toBeGreaterThanOrEqual(4.5);
    });
    it(`${theme}: 푸터 실행 상세 링크(--ac-accent)와 보조 글자(--ac-text-muted)가 배경·카드 표면에서 4.5 이상`, () => {
      for (const s of ["--ac-bg", "--ac-surface-1", "--ac-surface-2"]) {
        expect(contrast(val(block, "--ac-accent"), val(block, s)), `accent on ${s}`).toBeGreaterThanOrEqual(4.5);
        expect(contrast(val(block, "--ac-text-muted"), val(block, s)), `muted on ${s}`).toBeGreaterThanOrEqual(4.5);
      }
    });
    it(`${theme}: 말풍선 테두리(accent 35% 투명)는 장식이고 경계는 배경 대비 아님 — 진행 트리 가이드(--ac-border)는 표면 위에서 보인다(1.2 이상)`, () => {
      for (const s of ["--ac-bg", "--ac-surface-1"]) expect(contrast(val(block, "--ac-border"), val(block, s)), s).toBeGreaterThanOrEqual(1.2);
    });
  }
});

describe("글자 위계 (5.2R.52, ux-overhaul §15.5; 숫자 기대값은 5.2R.71에서 재기준)", () => {
  const cases = [
    ["다크", darkBlock, { text: 14.6, muted: 9.1, subtle: 6.4, s3muted: 7.0, border: 1.63 }],
    ["라이트", lightBlock, { text: 16.8, muted: 8.7, subtle: 5.8, s3muted: 7.18, border: 1.45 }],
  ] as const;
  for (const [theme, block, exp] of cases) {
    it(`${theme}: surface-1 대비가 명세 표와 ±0.1 이고 muted − subtle ≥ 2.0`, () => {
      const c = (t: string, s = "--ac-surface-1") => contrast(val(block, t), val(block, s));
      expect(c("--ac-text")).toBeCloseTo(exp.text, 0);
      expect(Math.abs(c("--ac-text") - exp.text)).toBeLessThanOrEqual(0.1);
      expect(Math.abs(c("--ac-text-muted") - exp.muted)).toBeLessThanOrEqual(0.1);
      expect(Math.abs(c("--ac-text-subtle") - exp.subtle)).toBeLessThanOrEqual(0.1);
      expect(c("--ac-text-muted") - c("--ac-text-subtle")).toBeGreaterThanOrEqual(2.0);
      expect(c("--ac-text-muted", "--ac-surface-3")).toBeGreaterThanOrEqual(exp.s3muted);
      expect(Math.abs(c("--ac-border") - exp.border)).toBeLessThanOrEqual(0.1);
    });
  }
  it("시스템 라이트 블록(prefers-color-scheme)이 라이트 값과 같다", () => {
    const m = /@media \(prefers-color-scheme: light\) \{([\s\S]*?)\n\}/.exec(css)![1]!;
    for (const t of ["--ac-text", "--ac-text-muted", "--ac-border"]) expect(val(m, t)).toBe(val(lightBlock, t));
  });
  it("굵기 토큰 400·600이 있고 CSS에 font-weight 500이 없다", () => {
    expect(css).toMatch(/--ac-fw-regular:\s*400/);
    expect(css).toMatch(/--ac-fw-strong:\s*600/);
    expect(css).not.toMatch(/font-weight:\s*500/);
  });
  it("PageHeader 제목은 20px(--ac-text-xl)", () => {
    expect(css).toMatch(/\.ac-pageheader-title\s*\{[^}]*font-size:\s*var\(--ac-text-xl\)/);
  });
});

describe("패키지 독립", () => {
  it("tokens.css에 graph-editor 클래스명(ac-ge-)이 없다", () => {
    expect(css).not.toContain("ac-ge-");
  });
  it("Button loading 은 라벨을 visibility 로 숨기지 않는다(접근성 이름 유지)", () => {
    const m = /\.ac-btn\[data-loading="true"\] > \.ac-btn-label[^{]*\{([^}]*)\}/.exec(css);
    expect(m).not.toBeNull();
    expect(m![1]).toContain("opacity: 0");
    expect(m![1]).not.toMatch(/visibility|display:\s*none/);
  });
  it("칩 테두리는 1.5px(queued 점선이 보이게)", () => {
    expect(ruleBody(".ac-status-chip")).toContain("border: 1.5px var(--ac-status-border-style");
  });
  it("범용 훅 클래스가 정의돼 있고 skipped 흐림은 ac-status-keep을 제외한다", () => {
    for (const c of ["ac-status-box", "ac-status-header", "ac-status-keep"]) expect(css, c).toContain(c);
    expect(css).toContain('.ac-status-box[data-status="skipped"] > :not(.ac-status-keep)');
  });
});

describe("외부 파일 의존 없음", () => {
  it("url()은 모두 data URI이고 @import가 없다", () => {
    expect(css).not.toMatch(/@import/);
    for (const m of css.matchAll(/url\(\s*["']?([^"')]+)/g)) expect(m[1]).toMatch(/^data:image\/svg\+xml,/);
  });
  it("컴포넌트 CSS에 hex 색을 직접 쓰지 않는다(토큰 정의 블록 밖)", () => {
    const afterTokens = css.slice(css.indexOf("/* ===== 5."));
    expect(afterTokens).not.toMatch(/#[0-9a-fA-F]{3,8}\b/);
  });
});
