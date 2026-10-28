import type { Project } from "@agent-console/contracts/projects";

const collator = new Intl.Collator("ko", { numeric: true, sensitivity: "base" });

/** 사이드바에 보일 프로젝트: 보관(등록 해제)된 것은 빼고 이름 오름차순(한국어, 숫자 자연 정렬). */
export function regionProjects(projects: readonly Project[]): Project[] {
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
