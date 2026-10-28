/**
 * 경로 가운데 줄임(docs/design/screen-projects.md §1.2). 순수 함수, DOM을 모른다.
 * 칸 수 근사: ASCII 1칸, 한글·전각·이모지 2칸, 결합 문자 0칸(1칸 ≈ mono 글자 0.6em ≈ 7.5px).
 */

/** mono 글자 한 칸의 근사 폭(px). */
export const CELL_WIDTH_PX = 7.5;

const segmenter: { segment(input: string): Iterable<{ segment: string }> } | null =
  typeof Intl !== "undefined" && "Segmenter" in Intl
    ? new (Intl as unknown as { Segmenter: new (l?: string, o?: { granularity: string }) => { segment(i: string): Iterable<{ segment: string }> } }).Segmenter(undefined, { granularity: "grapheme" })
    : null;

function codePointCells(cp: number): number {
  if (cp === 0x200d || (cp >= 0x300 && cp <= 0x36f) || (cp >= 0xfe00 && cp <= 0xfe0f) || (cp >= 0x20d0 && cp <= 0x20ff) || (cp >= 0x1ab0 && cp <= 0x1aff) || (cp >= 0x1dc0 && cp <= 0x1dff)) return 0;
  if (
    (cp >= 0x1100 && cp <= 0x115f) || (cp >= 0x2e80 && cp <= 0xa4cf) || (cp >= 0xac00 && cp <= 0xd7a3) || (cp >= 0xf900 && cp <= 0xfaff) ||
    (cp >= 0xfe30 && cp <= 0xfe6f) || (cp >= 0xff00 && cp <= 0xff60) || (cp >= 0xffe0 && cp <= 0xffe6) || (cp >= 0x1f300 && cp <= 0x1faff) ||
    (cp >= 0x20000 && cp <= 0x3fffd)
  ) return 2;
  return /\p{M}/u.test(String.fromCodePoint(cp)) ? 0 : 1;
}

/** 서로게이트 쌍·결합 문자 묶음(자소 묶음) 단위로 나눈다. */
function clusters(text: string): string[] {
  if (segmenter) return Array.from(segmenter.segment(text), (s) => s.segment);
  // Segmenter가 없는 환경: 결합 문자를 앞 글자에 붙인다.
  const out: string[] = [];
  for (const ch of text) {
    const cp = ch.codePointAt(0)!;
    if (out.length > 0 && codePointCells(cp) === 0) out[out.length - 1] += ch;
    else out.push(ch);
  }
  return out;
}

function clusterCells(cluster: string): number {
  let max = 0;
  for (const ch of cluster) max = Math.max(max, codePointCells(ch.codePointAt(0)!));
  return max;
}

/** 표시 칸 수(NFC 정규화 뒤). */
export function cells(text: string): number {
  let n = 0;
  for (const c of clusters(text.normalize("NFC"))) n += clusterCells(c);
  return n;
}

/** 폭(px)에서 쓸 수 있는 칸 수: `floor(폭 / 7.5) - 1`(최소 0). */
export function cellsForWidth(widthPx: number, cellWidthPx: number = CELL_WIDTH_PX): number {
  return Math.max(0, Math.floor(widthPx / cellWidthPx) - 1);
}

function splitPieces(path: string, sep: string): string[] {
  const out: string[] = [];
  let cur = "";
  for (const ch of path) {
    if (ch === sep && cur !== "") {
      out.push(cur);
      cur = "";
    }
    cur += ch;
  }
  if (cur !== "") out.push(cur);
  return out;
}

/** 조각 끝쪽에서 `budget`칸 안에 들어가는 만큼. */
function takeTail(text: string, budget: number): string {
  const cs = clusters(text);
  let used = 0;
  let i = cs.length;
  while (i > 0) {
    const w = clusterCells(cs[i - 1]!);
    if (used + w > budget) break;
    used += w;
    i -= 1;
  }
  return cs.slice(i).join("");
}

/**
 * 경로를 `maxCells`칸 안으로 줄인다. 들어가면 그대로 돌려준다.
 * 아니면 `머리…꼬리`: 꼬리(예산 `ceil((max-1)*0.65)`)는 마지막 폴더 이름을 항상 포함하고, 머리는 남는 칸에 앞 조각을 붙인다.
 * 구분자는 경로에 처음 나오는 `/` 또는 `\`를 따른다.
 *
 * @example middleEllipsis("/home/me/work/payments/services/api", 27) // "/home/me/work…/services/api"
 */
export function middleEllipsis(path: string, maxCells: number): string {
  if (cells(path) <= maxCells) return path;
  const budget = Math.floor(maxCells) - 1;
  if (budget <= 0) return maxCells >= 1 ? "…" : "";
  const text = path.normalize("NFC");
  const sepMatch = /[\\/]/.exec(text);
  const sep = sepMatch ? sepMatch[0] : "/";
  const trailing = text.length > 1 && text.endsWith(sep) ? sep : "";
  const pieces = splitPieces(trailing ? text.slice(0, -1) : text, sep);
  if (pieces.length === 0) pieces.push("");
  pieces[pieces.length - 1] += trailing;

  const tailBudget = Math.ceil(budget * 0.65);
  const last = pieces[pieces.length - 1]!;
  let tailStart = pieces.length - 1;
  let tail = last;
  if (cells(last) > tailBudget) {
    tail = takeTail(last, tailBudget);
    tailStart = pieces.length; // 마지막 조각을 잘랐으므로 머리는 마지막 조각 앞까지 쓸 수 있다
  } else {
    let used = cells(last);
    while (tailStart > 0) {
      const w = cells(pieces[tailStart - 1]!);
      if (used + w > tailBudget) break;
      used += w;
      tailStart -= 1;
      tail = pieces[tailStart]! + tail;
    }
  }

  const headBudget = budget - cells(tail);
  const headEnd = tailStart === pieces.length ? pieces.length - 1 : tailStart;
  let head = "";
  let used = 0;
  for (let i = 0; i < headEnd; i += 1) {
    const w = cells(pieces[i]!);
    if (used + w > headBudget) break;
    used += w;
    head += pieces[i];
  }
  return `${head}…${tail}`;
}
