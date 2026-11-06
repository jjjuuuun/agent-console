/**
 * 문구 표. 앱이 `messages` prop으로 일부만 덮어쓴다(번역·용어 바꾸기).
 * 상태 이름·문서 종류 이름·단계 이름은 여기에 없다 — 전부 서버 데이터(`label`·`title`)다.
 * `gap.<코드>`·`source.<출처>` 같은 키는 열린 문자열 계약 값에 붙이는 선택 문구이고, 표에 없으면 값 원문을 보인다.
 */
export const defaultMessages = {
  // 공통
  "common.unknown": "알 수 없음",
  "common.loading": "불러오는 중…",
  "common.close": "닫기",
  "common.readOnly": "읽기 전용",
  "common.blocked": "지금은 할 수 없습니다",
  // 스펙 목록
  "specs.list": "스펙 목록",
  "specs.empty.title": "스펙이 없습니다",
  "specs.empty.body": "새 스펙을 만들거나 폴더에서 문서를 가져오세요.",
  "specs.progress": "작업 {done}/{total}",
  "specs.ready": "준비 {n}",
  "specs.issues": "문제 {n}",
  "specs.stage": "지금 단계: {stage}",
  "specs.noTasks": "작업 없음",
  "specs.updated": "수정 {time}",
  "specs.sort.label": "스펙 정렬",
  // 문서 목록·편집기
  "docs.nav": "문서",
  "docs.empty": "문서가 없습니다",
  "docs.state": "상태: {state}",
  "docs.noState": "상태 없음",
  "editor.label": "문서 본문 편집기: {title}",
  "editor.preview": "미리보기",
  "editor.previewEmpty": "미리볼 내용이 없습니다.",
  "editor.mode.edit": "편집",
  "editor.mode.preview": "미리보기",
  "editor.mode.split": "나란히",
  "editor.mode.group": "보기 방식",
  "editor.save": "저장",
  "editor.saving": "저장 중…",
  "editor.dirty": "저장하지 않은 변경이 있습니다",
  "editor.saved": "저장됨",
  "editor.composing": "입력 중에는 저장을 미룹니다",
  "editor.missing.title": "문서 파일이 없습니다",
  "editor.missing.body": "{file} 파일이 사라졌습니다. 앱은 파일을 대신 만들지 않습니다.",
  "editor.missing.create": "빈 파일로 만들기",
  "editor.readOnly.title": "읽기 전용",
  "editor.readOnly.body": "이 문서는 고칠 수 없습니다.",
  "editor.conflict.title": "다른 곳에서 문서가 바뀌었습니다",
  "editor.conflict.body": "저장하면 바뀐 내용을 덮어씁니다. 먼저 최신 내용을 불러오거나 내 변경을 덮어쓰세요.",
  "editor.conflict.reload": "최신 내용 불러오기",
  "editor.conflict.overwrite": "내 변경으로 덮어쓰기",
  "editor.copyMine": "내 변경 복사",
  "editor.compare": "변경 비교",
  "editor.compare.head": "{before} ↔ {after}",
  "editor.compare.before": "저장된 내용",
  "editor.compare.after": "지금 편집 중인 내용",
  "editor.compare.same": "비교할 차이가 없습니다.",
  "editor.external.body": "이 문서가 다른 곳에서 바뀌었습니다. 저장하면 충돌이 납니다.",
  "editor.goto": "줄로 이동",
  "editor.goto.label": "줄 번호",
  "editor.goto.go": "이동",
  "editor.goto.invalid": "문서에 없는 줄 번호입니다.",
  "editor.goto.issue": "줄로 이동",
  "editor.tooLarge": "크기 제한을 넘어 읽기 전용입니다",
  "editor.issues": "문서 점검 결과",
  "editor.empty": "문서를 고르세요",
  // 작업 표
  "tasks.table": "작업 표",
  "tasks.empty.title": "작업이 없습니다",
  "tasks.empty.body": "작업 문서에 작업 줄을 쓰면 여기에 나타납니다.",
  "tasks.noSyntax.title": "작업 문법이 없습니다",
  "tasks.noSyntax.body": "작업 줄을 읽는 문법이 꺼져 있거나 비어 있습니다. 규칙 탭에서 문법을 켜거나 정하세요.",
  "tasks.noSyntax.action": "규칙 열기",
  "tasks.stage.none": "단계 없음",
  "tasks.stage.progress": "{done}/{total}",
  "tasks.stage.toggle": "{stage} 단계 접기·펼치기",
  "tasks.col.title": "작업",
  "tasks.col.status": "상태",
  "tasks.col.links": "연결",
  "tasks.ready": "준비됨",
  "tasks.blocked": "막힘",
  "tasks.row": "{title}, 상태 {status}, {readiness}",
  "tasks.expand": "상세 펴기",
  "tasks.collapse": "상세 접기",
  "tasks.detail.document": "문서",
  "tasks.detail.line": "{line}번째 줄",
  "tasks.detail.requirements": "요구",
  "tasks.detail.dependencies": "의존",
  "tasks.detail.fields": "필드",
  "tasks.detail.open": "문서에서 열기",
  "tasks.detail.issues": "문제",
  "tasks.status.change": "{title}의 상태 바꾸기",
  "tasks.status.menu": "상태 목록",
  "tasks.conflict.title": "줄이 바뀌었습니다",
  "tasks.conflict.body": "다른 곳에서 이 줄이 바뀌어 최신 줄로 다시 그렸습니다. 다시 시도하세요.",
  "tasks.conflict.latest": "최신 줄",
  "tasks.runChip": "{ref}, {status}",
  "tasks.runChip.open": "{ref} 열기",
  "tasks.moreFields": "+{n}",
  "tasks.select.row": "{title} 선택",
  "tasks.select.all": "보이는 준비된 작업 모두 선택",
  "tasks.select.count": "{n}개 선택",
  "tasks.select.clear": "선택 해제",
  "tasks.rowMenu": "{title} 메뉴",
  // 계획
  "plan.graph": "작업 계획 그래프",
  "plan.empty": "계획할 작업이 없습니다",
  "plan.layout": "배치를 계산하는 중…",
  "plan.layoutFailed": "자동 배치를 쓸 수 없어 층별로 놓았습니다",
  "plan.critical": "병목",
  "plan.criticalHint": "가장 긴 의존 사슬",
  "plan.ready": "준비됨",
  "plan.blocked": "막힘",
  "plan.cycle": "순환",
  "plan.node": "{title}, {layer}번째 묶음, {flags}",
  "plan.bundles": "병렬 묶음",
  "plan.bundle": "묶음 {n}",
  "plan.bundleCount": "{n}개 작업을 동시에 할 수 있습니다",
  "plan.bundlesEmpty": "묶음이 없습니다",
  "plan.cycles": "순환 의존",
  "plan.cycleLine": "{keys}",
  "plan.truncated": "작업이 많아 앞의 {n}개만 그렸습니다",
  "plan.criticalPath": "병목 경로 {n}단계",
  // 추적
  "trace.table": "요구-작업 추적 표",
  "trace.empty.title": "추적할 요구가 없습니다",
  "trace.empty.body": "요구 문서에 요구 줄을 쓰면 여기에 나타납니다.",
  "trace.col.requirement": "요구",
  "trace.col.tasks": "작업",
  "trace.col.runs": "실행",
  "trace.col.verification": "검증",
  "trace.col.gaps": "빈 곳",
  "trace.noGaps": "빈 곳 없음",
  "trace.filter.gaps": "빈 곳만 보기",
  "trace.openTask": "{key} 작업 열기",
  "trace.openRequirement": "{id} 요구 열기",
  "trace.noVerification": "검증 없음",
  "trace.orphans": "연결되지 않은 것",
  "trace.orphan.tasks": "요구 없는 작업 {n}",
  "trace.orphan.unknownRefs": "없는 요구를 가리키는 작업 {n}",
  "trace.orphan.unknownLinks": "없는 작업을 가리키는 연결 {n}",
  "trace.row": "{id}, 작업 {tasks}, {gaps}",
  // 관문
  "gate.title": "관문에 막혔습니다",
  "gate.fallback": "{id} 관문 조건을 만족하지 않습니다.",
  "gate.documents": "확인할 문서",
  "gate.openDocument": "{title} 열기",
  "gate.dismiss": "알림 닫기",
  "gate.action": "가져와서 실행",
  // 규칙 출처
  "source.label": "출처: {source}",
  "source.tip": "이 값이 어디에서 왔는지",
  // 상태 칩
  "chip.noLabel": "이름 없음",
} as const;

export type SddViewMessageKey = keyof typeof defaultMessages;
/** 문구 표. 기본 키는 모두 있고 앱이 더한 키도 허용한다. */
export type SddViewMessages = { [K in SddViewMessageKey]: string } & Readonly<Record<string, string>>;

/** 틀의 `{이름}` 자리를 값으로 바꾼다. 없는 이름은 그대로 둔다. */
export function formatMessage(template: string, vars: Readonly<Record<string, string | number>> = {}): string {
  return template.replace(/\{(\w+)\}/g, (m, k: string) => (k in vars ? String(vars[k]) : m));
}

/** 부분 문구 표를 기본 문구와 합친다. */
export function resolveMessages(partial?: Readonly<Record<string, string>>): SddViewMessages {
  return partial ? ({ ...defaultMessages, ...partial } as SddViewMessages) : (defaultMessages as SddViewMessages);
}

/** 키로 문구를 찾는다. 없으면 `fallback`(보통 모르는 계약 어휘 원문). */
export function messageOr(messages: Readonly<Record<string, string>>, key: string, fallback: string): string {
  return messages[key] ?? fallback;
}
