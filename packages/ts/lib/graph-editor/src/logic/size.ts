/** tokens.md 4절: 노드 박스 크기 산정(순수 함수). 고정 픽셀 표 없음. */

/** 글자 하나의 폭(em). 한글·한자·전각 1.0, 대문자·숫자 0.62, 소문자 0.56, 공백 0.3, 그 외 0.6. */
function glyphEm(ch: string): number {
  const c = ch.codePointAt(0) ?? 0;
  if (
    (c >= 0x1100 && c <= 0x11ff) ||
    (c >= 0x2e80 && c <= 0xa4cf) ||
    (c >= 0xac00 && c <= 0xd7af) ||
    (c >= 0xf900 && c <= 0xfaff) ||
    (c >= 0xff00 && c <= 0xffef)
  )
    return 1;
  if (ch === " ") return 0.3;
  if (ch >= "A" && ch <= "Z") return 0.62;
  if (ch >= "0" && ch <= "9") return 0.62;
  if (ch >= "a" && ch <= "z") return 0.56;
  return 0.6;
}

/** 추정 텍스트 폭(px). */
export function textWidth(text: string, fontSize: number): number {
  let em = 0;
  for (const ch of text) em += glyphEm(ch);
  return em * fontSize;
}

const ceil8 = (n: number): number => Math.ceil(n / 8) * 8;

export const NODE_MIN_WIDTH = 160;
export const NODE_MAX_WIDTH = 320;
export const NODE_MIN_HEIGHT = 72;
export const PORT_ROW_HEIGHT = 24;

export interface MeasureInput {
  label: string;
  typeTitle: string;
  inputLabels: readonly string[];
  outputLabels: readonly string[];
  /** 실행 요약 줄이 있는가 */
  hasSummary?: boolean;
}

export interface NodeSize {
  width: number;
  height: number;
  /** 제목이 2줄로 접히는가 */
  labelLines: 1 | 2;
}

/** 노드 폭·높이 초기 추정값(자동 배치·미니맵·테스트용. 실제 높이는 DOM 측정). */
export function measureNodeSize(input: MeasureInput): NodeSize {
  const maxLabel = (labels: readonly string[]): number =>
    labels.reduce((m, l) => Math.max(m, textWidth(l, 12)), 0);
  const titleW = textWidth(input.label, 13) + 20 + 8 + 16 + 24;
  const subtitleW = textWidth(input.typeTitle, 12) + 24;
  const portsW = maxLabel(input.inputLabels) + maxLabel(input.outputLabels) + 2 * 12 + 24;
  const width = Math.min(NODE_MAX_WIDTH, Math.max(NODE_MIN_WIDTH, ceil8(Math.max(titleW, subtitleW, portsW))));

  const availTitle = width - (20 + 8 + 16 + 24);
  const labelLines: 1 | 2 = textWidth(input.label, 13) > availTitle ? 2 : 1;
  const headerH = 8 + labelLines * 18 + 4 + 16 + 8;
  const rows = Math.max(input.inputLabels.length, input.outputLabels.length);
  const portsH = rows * PORT_ROW_HEIGHT + 8;
  const summaryH = input.hasSummary ? 20 : 0;
  return { width, height: Math.max(NODE_MIN_HEIGHT, headerH + portsH + summaryH), labelLines };
}

export const CHIP_MIN_WIDTH = 144;
export const CHIP_MAX_WIDTH = 240;
export const CHIP_HEIGHT = 40;

/** 칩 카드(tokens 4.6): 헤더 한 줄(아이콘 + label + 타입 제목). 폭 144~240. */
export function measureChipSize(label: string, typeTitle: string): NodeSize {
  const w = textWidth(label, 13) + textWidth(typeTitle, 12) + 20 + 8 + 8 + 24;
  return { width: Math.min(CHIP_MAX_WIDTH, Math.max(CHIP_MIN_WIDTH, ceil8(w))), height: CHIP_HEIGHT, labelLines: 1 };
}
