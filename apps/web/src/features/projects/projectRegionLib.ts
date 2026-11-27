import type { Project, ProjectView } from "@agent-console/contracts/projects";
import keymap from "./hangul2set.json";

/** 사이드바에 보일 프로젝트: 보관(등록 해제)된 것은 빼고 이름 오름차순(화면 언어, 숫자 자연 정렬). */
export function regionProjects(projects: readonly Project[], language: string): Project[] {
  const collator = new Intl.Collator(language, { numeric: true, sensitivity: "base" });
  return projects.filter((p) => p.archived !== true).sort((a, b) => collator.compare(a.name, b.name) || collator.compare(a.id, b.id));
}

/** 이니셜 한 글자: 이름의 첫 묶음(글자 단위)을 대문자로. 비면 `·`. */
export function projectInitial(name: string | undefined): string {
  const text = (name ?? "").trim();
  if (text === "") return "·";
  const Seg = (Intl as { Segmenter?: new (l?: string, o?: { granularity: "grapheme" }) => { segment(s: string): Iterable<{ segment: string }> } }).Segmenter;
  const first = Seg === undefined ? Array.from(text)[0] : [...new Seg(undefined, { granularity: "grapheme" }).segment(text)][0]?.segment;
  return (first ?? "·").toUpperCase();
}

/** 접힘 저장 값 해석: `"1"`만 접힘, 그 밖(없음·읽기 실패)은 펼침. */
export function parseCollapsed(raw: string | null): boolean {
  return raw === "1";
}

/** 사이드바에 보일 프로젝트 보기: 보관(등록 해제)된 것은 빼고 이름순. */
export function regionViews(views: readonly ProjectView[], language: string): ProjectView[] {
  const collator = new Intl.Collator(language, { numeric: true, sensitivity: "base" });
  return views.filter((v) => v.project.archived !== true).sort((a, b) => collator.compare(a.project.name, b.project.name) || collator.compare(a.project.id, b.project.id));
}

/** type-ahead 비교용 정규화: 호환 자모(ㅎ)와 완성 글자(하)가 같은 첫 자모로 비교되게 풀고 소문자로. */
const foldForMatch = (text: string): string => text.normalize("NFKD").toLowerCase();

/** type-ahead 묶음이 이어지는 시간(ms). 이보다 오래 쉬면 새로 시작한다. */
export const TYPE_AHEAD_RESET_MS = 700;

/**
 * 글자 입력으로 갈 항목을 고른다(이름 앞글자, 한글 자모 입력 포함). 한 글자면 지금 다음 항목부터, 여러 글자면 지금 항목부터 찾아 한 바퀴 돈다.
 *
 * @param names 항목 이름들(화면 순서)
 * @param active 지금 포커스된 항목 번호(없으면 -1)
 * @param typed 지금까지 입력한 글자
 * @returns 이동할 번호, 없으면 -1
 */
export function typeAheadIndex(names: readonly string[], active: number, typed: string): number {
  if (names.length === 0 || typed === "") return -1;
  const needle = foldForMatch(typed);
  const from = typed.length === 1 ? active + 1 : Math.max(active, 0);
  for (let k = 0; k < names.length; k++) {
    const i = (from + k) % names.length;
    if (foldForMatch(names[i] ?? "").startsWith(needle)) return i;
  }
  return -1;
}

/**
 * 한글 입력기가 켜져 있으면 키 입력이 글자가 아니라 `key: "Process"`로 오므로, 물리 키(`code`)를 두벌식 자판의 자모로 바꿔 type-ahead에 쓴다.
 * 자판 배열 데이터(`hangul2set.json`)다(다른 배열이 필요하면 그 파일만 바꾼다).
 */
export const HANGUL_2SET_BY_CODE: Readonly<Record<string, string>> = keymap;

/** type-ahead에 넣을 글자: 평소엔 `key`, 입력기 처리 중(`Process`)이면 물리 키의 자모. 글자가 아니면 undefined. */
export function typeAheadChar(e: { key: string; code: string; ctrlKey: boolean; metaKey: boolean; altKey: boolean; isComposing: boolean }): string | undefined {
  if (e.ctrlKey || e.metaKey || e.altKey) return undefined;
  if (e.key === "Process") return HANGUL_2SET_BY_CODE[e.code];
  if (e.isComposing || e.key.length !== 1 || e.key === " ") return undefined;
  return e.key;
}
