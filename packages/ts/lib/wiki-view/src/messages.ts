/**
 * 문구 표. 앱이 `messages` prop으로 일부만 덮어쓴다(번역·용어 바꾸기). `{이름}` 자리는 `formatMessage`가 채운다.
 * 이 표에는 위키 이름·페이지 경로·링크 패턴·규칙 id 같은 사용자 데이터가 없다. 열린 문자열 값(동작·종류·심각도)의 이름은 `WikiDisplay`가 준다.
 */
export const defaultMessages = {
  "common.close": "닫기",
  "common.cancel": "취소",
  "time.now": "방금",
  "time.minutes": "{n}분 전",
  "time.hours": "{n}시간 전",
  "time.days": "{n}일 전",

  "author.run": "실행 {id}",
  "author.tip.agent": "에이전트 {id}",
  "author.tip.node": "노드 {path}",
  "author.tip.run": "실행 {id}",

  "tree.label": "페이지 트리",
  "tree.empty": "페이지가 없습니다",
  "tree.noMatch": "조건에 맞는 페이지가 없습니다",
  "tree.folder": "폴더 {name}, 페이지 {n}개",
  "tree.home": "첫 페이지",
  "tree.orphan": "고아 페이지",
  "tree.broken": "끊긴 링크 {n}개",
  "tree.dirty": "저장 안 됨",
  "tree.truncated": "일부 페이지만 불러왔습니다. 본문 검색을 쓰세요.",
  "tree.truncated.total": "페이지 {total}개 중 {max}개까지만 불러왔습니다. 본문 검색을 쓰세요.",

  "page.empty": "이 페이지는 비어 있습니다.",
  "link.broken.tip": "끊긴 링크: ‘{target}’ 페이지가 없습니다",
  "link.broken.popover": "끊긴 링크",
  "link.broken.body": "‘{target}’ 페이지가 없습니다",
  "link.broken.create": "이 페이지 만들기",
  "link.scheme.off": "연결된 기능이 꺼져 있습니다",
  "link.outside.tip": "위키 폴더 밖을 가리키는 링크라 열지 않습니다",

  "outlinks.label": "나가는 링크",
  "outlinks.empty": "이 페이지에서 나가는 링크가 없습니다",
  "outlinks.locate": "본문에서 ‘{label}’ 위치로 이동",
  "outlinks.create": "‘{label}’ 페이지 만들기",
  "outlinks.create.tip": "이 페이지 만들기",

  "history.label": "페이지 기록",
  "history.empty": "아직 기록이 없습니다. 저장하거나 다시 읽으면 첫 버전이 만들어집니다.",
  "history.current": "현재",
  "history.compare": "v{v} 비교",
  "history.compare.tip": "비교",
  "history.restore": "v{v}(으)로 되돌리기",
  "history.restore.tip": "되돌리기",
  "history.pruned": "오래된 버전은 보관 수 제한으로 지워졌습니다",
  "history.unavailable.title": "이 위키는 기록을 저장하지 않습니다",
  "history.unavailable.body": "페이지 기록과 되돌리기는 프로젝트 기록 저장소가 있어야 합니다. 페이지 편집과 검색은 그대로 됩니다.",
  "history.unavailable.settings": "프로젝트 설정 보기",

  "diff.label": "v{v} 비교",
  "diff.base": "비교 기준",
  "diff.base.previous": "이전 버전과",
  "diff.base.current": "현재 본문과",
  "diff.noPrevious": "이전 버전이 없습니다 — 현재 본문과 비교합니다",
  "diff.same": "비교할 차이가 없습니다.",

  "graph.label": "링크 그래프, 노드 {n}개. 방향키로 이웃 노드로 이동, Enter로 열기, Shift+Enter 또는 C로 중심 삼기",
  "graph.empty": "그래프에 그릴 페이지가 없습니다",
  "graph.layoutFailed": "자동 배치를 쓸 수 없어 격자로 놓았습니다",
  "graph.truncated": "일부만 표시했습니다",
  "graph.truncated.total": "{total}개 중 {n}개만 표시했습니다",

  "linklist.label": "연결 목록",
  "linklist.filter": "제목·경로 거르기",
  "linklist.empty": "표시할 페이지가 없습니다",
  "linklist.noMatch": "조건에 맞는 항목이 없습니다",
  "linklist.expand": "{title} 펼치기",
  "linklist.collapse": "{title} 접기",
  "linklist.center": "현재",
  "linklist.orphan": "고아",
  "linklist.broken": "끊긴 링크",
  "linklist.out": "나가는 링크",
  "linklist.in": "들어오는 링크",
  "linklist.truncated": "일부만 표시했습니다",

  "lint.label": "점검 결과",
  "lint.summary": "심각도별 개수",
  "lint.none": "문제가 없습니다",
  "lint.col.severity": "심각도",
  "lint.col.code": "코드",
  "lint.col.page": "페이지",
  "lint.col.line": "줄",
  "lint.col.message": "메시지",
  "lint.col.rule": "규칙",
  "lint.filter.severity": "{severity}만 보기",
  "lint.filter.code": "코드 거르기",
  "lint.filter.codeAll": "모든 코드",
  "lint.filter.page": "페이지 경로 거르기",
  "lint.noMatch": "조건에 맞는 항목이 없습니다",
  "lint.clearFilter": "거르기 지우기",

  "search.label": "검색 결과",
  "search.empty": "‘{query}’와 맞는 페이지가 없습니다",
  "search.degraded": "검색이 파일을 하나씩 읽는 방식으로 동작합니다. 페이지가 많으면 오래 걸리거나 일부만 검색됩니다.",
  "search.truncated": "결과가 많아 일부만 표시했습니다",

  "new.path": "경로",
  "new.suggestions": "폴더 제안",
  "new.exists": "이미 있는 페이지입니다",
  "new.exists.open": "열기",
  "new.title": "제목",
  "new.title.hint": "비우면 문서 안의 제목이나 파일 이름으로 정해집니다",
  "new.template": "페이지 틀",
  "new.template.blank": "빈 페이지",
  "new.template.path": "경로 틀: {path}",
  "new.variables": "틀에 넣을 값",
  "new.prefilled": "본문 {n}자 가져옴",
  "new.submit": "만들기",
  "new.submitting": "만드는 중…",

  "move.from": "현재",
  "move.to": "새 경로",
  "move.rewrite": "이 페이지를 가리키는 링크도 고치기",
  "move.rewrite.hint": "링크 글자 부분만 바뀌고 나머지 서식은 그대로입니다.",
  "move.pages": "바뀔 페이지",
  "move.loading": "불러오는 중…",
  "move.totals": "페이지 {pages} · 링크 {links}곳",
  "move.count": "{n}곳",
  "move.willBreak": "링크는 고치지 않습니다. {pages}개 페이지의 링크 {links}곳이 끊긴 링크가 됩니다.",
  "move.conflicts": "{done}개 페이지의 링크를 고쳤습니다. {skipped}개 페이지는 그사이 바뀌어 고치지 못했습니다.",
  "move.conflicts.label": "고치지 못한 페이지",
  "move.conflict.row": "그사이 바뀌어 건너뜁니다",
  "move.conflict.open": "열기",
  "move.submit": "이름 바꾸기",
  "move.submitting": "바꾸는 중…",

  "rules.label": "쓰는 규칙",
  "rules.empty": "쓰는 규칙이 없습니다. 쓰기 규칙·점검 규칙·지침이 없는 위키입니다.",
  "rules.missing": "‘{id}’ 규칙이 이 프로젝트에 없습니다",
  "rules.duplicate": "‘{id}’ 규칙이 두 번 들어 있습니다",
  "rules.sum.write": "쓰기 {n}",
  "rules.sum.lint": "점검 {n}",
  "rules.sum.templates": "틀 {n}",
  "rules.sum.instructions": "지침 있음",
  "rules.open": "{name} 열기",
  "rules.up": "{name} 위로",
  "rules.up.tip": "위로 (Alt+↑)",
  "rules.down": "{name} 아래로",
  "rules.down.tip": "아래로 (Alt+↓)",
  "rules.remove": "빼기",
  "rules.remove.label": "{name} 빼기",
  "rules.add": "규칙 더하기",
  "rules.add.none": "더할 수 있는 규칙이 없습니다",
  "rules.import": "공용에서 가져오기…",

  "syntax.empty": "표시할 문법 값이 없습니다",
  "syntax.emptyList": "비어 있음",
  "syntax.noLinks": "링크 규칙 없음 — 그래프·백링크·끊긴 링크 점검이 꺼져 있습니다",
  "syntax.source.rules": "규칙 {id}",
  "syntax.source.open": "열기",
} as const;

export type WikiViewMessageKey = keyof typeof defaultMessages;
/** 문구 표. 기본 키는 모두 있고 앱이 더한 키도 허용한다. */
export type WikiViewMessages = { [K in WikiViewMessageKey]: string } & Readonly<Record<string, string>>;

/** 틀의 `{이름}` 자리를 값으로 바꾼다. 없는 이름은 그대로 둔다. */
export function formatMessage(template: string | undefined, vars: Readonly<Record<string, string | number>> = {}): string {
  return (template ?? "").replace(/\{(\w+)\}/g, (m, k: string) => (k in vars ? String(vars[k]) : m));
}

/** 부분 문구 표를 기본 문구와 합친다. */
export function resolveMessages(partial?: Readonly<Record<string, string>>): WikiViewMessages {
  return partial ? ({ ...defaultMessages, ...partial } as WikiViewMessages) : (defaultMessages as WikiViewMessages);
}
