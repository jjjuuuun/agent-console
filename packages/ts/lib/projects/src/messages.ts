/**
 * 프로젝트 2 문구 표(한국어 원본, screen-projects §12.2). 화면 문구는 키로만 다루고 이 표는 기본값이다.
 * 앱이 같은 키로 덮어쓸 수 있다(`createProjectsText`). 문구에 모듈·기능·구성 종류 이름을 고정하지 않는다:
 * 종류 이름은 `{kind}` 같은 자리표시로, 구성 폴더 이름은 `{dir}`로 받는다.
 * 폐기어(U-16: 작업 폴더·사용 중·빼기·가져온 구성 …)는 쓰지 않는다 — `RETIRED_TERMS`가 그 목록(데이터)이다.
 */

export const DEFAULT_PROJECT_MESSAGES = {
  "projects.status.ready": "정상",
  "projects.status.folder_missing": "폴더 없음",
  "projects.status.not_a_directory": "폴더 아님",
  "projects.status.no_access": "권한 없음",
  "projects.status.folder_unset": "폴더 미지정",
  "projects.status.folder_conflict": "폴더 겹침",
  "projects.status.manifest_invalid": "설정 파일 오류",
  "projects.status.archived": "등록 해제됨",
  "projects.status.readonly": "읽기 전용 폴더",
  "projects.status.unknown": "프로젝트 상태: {status}",
  "projects.status.blocked_reason": "{status}라서 사용할 수 없습니다",
  "projects.dir_fallback": "구성 폴더",
  "projects.blocked.new_chat": "폴더를 쓸 수 없어 새 채팅을 시작할 수 없습니다",
  "projects.blocked.run": "폴더를 쓸 수 없어 실행할 수 없습니다",
  "projects.blocked.records_readonly": "이 폴더에 쓸 수 없어 대화·실행 기록을 저장할 수 없습니다",
  "projects.blocked.records_newer": "더 새 버전의 앱이 이 폴더의 기록을 만들어 이 앱에서는 시작할 수 없습니다. 앱을 업데이트하세요",
  "projects.blocked.records_unavailable": "이 폴더의 기록 파일을 쓸 수 없어 시작할 수 없습니다",
  "projects.blocked.records_move": "기록을 저장할 수 없는 폴더라 옮길 수 없습니다",
  "projects.blocked.archived": "등록 해제된 프로젝트의 기록은 읽기만 가능합니다",
  "projects.blocked.copy_in": "폴더를 쓸 수 없어 구성을 가져올 수 없습니다",
  "projects.blocked.edit": "폴더를 쓸 수 없어 이 프로젝트의 구성을 고칠 수 없습니다",
  "projects.blocked.manifest": "프로젝트 설정 파일을 읽을 수 없어 사용할 수 없습니다",
  "projects.blocked.login": "로그인이 필요합니다",
  "projects.config_readonly": "이 폴더에는 쓸 수 없어 구성을 가져오거나 고칠 수 없습니다(보기는 됩니다)",
  "space.library": "공용",
  "space.library_tip": "프로젝트와 독립된 기본 구성입니다. 프로젝트로 가져가면 사본이 만들어집니다.",
  "space.project": "프로젝트: {name}",
  "space.project_note": "이 프로젝트의 사본입니다. 수정은 공용 구성에 영향을 주지 않습니다.",
  "space.view_in_project": "프로젝트 홈의 구성 보기",
  "space.open_home": "프로젝트 홈으로",
  "space.view_library": "공용 구성 보기",
  "space.back_home": "← {name} 홈",
  "space.save_location": "저장 위치: 프로젝트 {name}",
  "copy.state.absent": "없음",
  "copy.state.identical": "같은 내용이 이미 있음",
  "copy.state.different": "내용이 다름",
  "copy.action.copy": "복사",
  "copy.action.reuse": "그대로 쓰기",
  "copy.action.overwrite": "덮어쓰기",
  "copy.action.rename": "새 이름으로 추가",
  "copy.action.skip": "가져오지 않기",
  "copy.action.skip_keep": "가져오지 않기(이 프로젝트의 것을 씀)",
  "copy.action.choose": "선택하세요",
  "copy.skip_warn": "‘{by}’은(는) {id}가 없어 실행 전에 막힙니다",
  "copy.status.copied": "복사함",
  "copy.status.reused": "그대로 씀",
  "copy.status.overwritten": "덮어씀",
  "copy.status.renamed": "새 이름으로 추가함 → {id}",
  "copy.status.skipped": "건너뜀",
  "copy.status.conflict": "계획 뒤에 바뀌어 적용하지 않았습니다",
  "copy.import.title": "공용에서 가져오기 — {name}",
  "copy.save.title": "공용에 저장 — {name}",
  "copy.move.title": "공용 구성 옮기기 — {name}",
  "copy.import.intro": "공용 구성의 사본을 {name} 폴더({dir})에 만듭니다. 가져온 뒤에는 서로 독립입니다. 공용을 고쳐도 이 프로젝트의 사본은 바뀌지 않습니다.",
  "copy.save.intro": "{name}의 사본을 공용 구성에 복사합니다. 복사한 뒤에는 서로 독립입니다.",
  "copy.pick.search": "검색",
  "copy.pick.search_placeholder": "검색…",
  "copy.pick.kind": "종류",
  "copy.pick.kind_all": "전체",
  "copy.pick.list": "복사할 구성",
  "copy.pick.exists": "이 프로젝트에 같은 이름이 있음",
  "copy.pick.exists_library": "공용에 같은 이름이 있음",
  "copy.pick.empty_library": "공용 구성이 없습니다. 구성 화면에서 먼저 만드세요.",
  "copy.pick.empty_project": "이 프로젝트에는 구성이 없습니다",
  "copy.pick.no_match": "‘{query}’와 맞는 구성이 없습니다",
  "copy.pick.loading": "구성 목록을 불러오는 중…",
  "copy.pick.failed": "구성 목록을 불러오지 못했습니다",
  "copy.pick.to_library": "공용 구성 화면으로",
  "copy.pick.selected": "{n}개 선택",
  "copy.pick.next": "다음",
  "copy.plan.counts": "요청한 항목 {requested}개 · 함께 가져올 항목 {referenced}개",
  "copy.plan.include_refs": "함께 가져올 항목도 포함",
  "copy.plan.refs_off_note": "연결된 항목을 빼면 이 구성은 실행 전에 막힐 수 있습니다.",
  "copy.plan.col_item": "항목",
  "copy.plan.col_state": "대상 상태",
  "copy.plan.col_action": "처리",
  "copy.plan.include_row": "{name} 가져오기",
  "copy.plan.reason_requested": "요청",
  "copy.plan.reason_referenced": "‘{by}’이(가) 사용",
  "copy.plan.need_choice": "내용이 다른 항목 {n}개의 처리 방법을 고르세요.",
  "copy.plan.bad_new_id": "새 이름을 확인하세요.",
  "copy.plan.all_skipped": "가져올 항목이 없습니다.",
  "copy.plan.empty": "복사할 항목이 없습니다.",
  "copy.plan.overwrite_warn": "이 프로젝트에서 바꾼 내용이 사라집니다. 편집기의 버전 기록에서 되돌릴 수 있습니다.",
  "copy.plan.overwrite_warn_library": "공용 구성의 내용이 사라집니다. 편집기의 버전 기록에서 되돌릴 수 있습니다.",
  "copy.plan.new_id": "새 이름(id)",
  "copy.plan.new_id_help": "이 묶음 안의 연결이 새 이름으로 바뀝니다.",
  "copy.plan.new_id_empty": "새 이름을 입력하세요.",
  "copy.plan.new_id_invalid": "영문·숫자·-·_만 쓸 수 있고 첫 글자는 영문이나 숫자여야 합니다.",
  "copy.plan.new_id_taken": "이미 있는 이름입니다.",
  "copy.plan.remove_source": "복사한 뒤 공용에서 지우기",
  "copy.plan.remove_source_help": "끄면 공용에는 남고 옛 프로젝트 필드만 지워집니다.",
  "copy.plan.loading": "복사 계획을 만드는 중…",
  "copy.plan.failed": "복사 계획을 만들지 못했습니다",
  "copy.plan.retry": "다시 시도",
  "copy.independent_note": "복사한 뒤에는 서로 독립입니다. 알림이나 자동 동기화는 없습니다.",
  "copy.back": "← 뒤로",
  "copy.cancel": "취소",
  "copy.close": "닫기",
  "copy.submit.import": "가져오기 ({n})",
  "copy.submit.save": "저장 ({n})",
  "copy.submit.move": "옮기기 ({n})",
  "copy.submit.run": "가져오고 실행 ({n})",
  "copy.submit.busy": "복사하는 중…",
  "copy.result.partial": "{total}개 중 {ok}개를 가져왔습니다",
  "copy.result.replan": "다시 계획",
  "copy.result.replan_all": "다시 계획 ({n})",
  "copy.result.error_prefix": "적용하지 못했습니다",
  "copy.result.toast_one": "‘{name}’을(를) 가져왔습니다",
  "copy.result.toast_many": "‘{name}’ 외 {n}개를 가져왔습니다",
  "copy.result.open": "열기",
  "copy.import_to_project": "이 프로젝트로 가져오기…",
  "copy.import_selected": "선택한 {n}개를 이 프로젝트로 가져오기…",
  "copy.save_to_library": "공용에 저장…",
  "copy.summary": "복사 {copy} · 그대로 쓰기 {reuse} · 덮어쓰기 {overwrite} · 새 이름 {rename} · 건너뜀 {skip}",
} as const satisfies Record<string, string>;

export type ProjectMessageKey = keyof typeof DEFAULT_PROJECT_MESSAGES;

/** 화면 문구에 쓰지 않는 말(U-16). 5.7R.35 정적 검사가 읽는 데이터이며, 이 패키지 테스트는 기본 문구가 이 말을 쓰지 않는지 확인한다. */
export const RETIRED_TERMS: readonly string[] = [
  "작업 폴더",
  "작업 경로",
  "서버 작업 폴더",
  "프로젝트 만들기",
  "공용으로 옮기기",
  "사용 중",
  "빼기",
  "가져온 구성",
  "원본 없음",
];

export type MessageParams = Readonly<Record<string, string | number>>;

/** `{이름}` 자리를 채운다. 없는 값은 자리표시를 그대로 둔다. */
export function formatMessage(template: string, params: MessageParams = {}): string {
  return template.replace(/\{(\w+)\}/g, (whole, name: string) => (name in params ? String(params[name]) : whole));
}

/** 키 + 자리 값 한 쌍. 판단 함수가 문구 대신 돌려주고, 화면이 `text(ref)`로 바꾼다. */
export interface MessageRef {
  key: string;
  params?: MessageParams;
}

export type ProjectsText = (ref: MessageRef | string, params?: MessageParams) => string;

/**
 * 문구 변환 함수를 만든다. `overrides`가 기본 표를 덮어쓰고, 모르는 키는 키 문자열 그대로 돌려준다
 * (누락이 화면에서 보이게).
 */
export function createProjectsText(overrides: Readonly<Record<string, string>> = {}): ProjectsText {
  const table: Readonly<Record<string, string>> = { ...DEFAULT_PROJECT_MESSAGES, ...overrides };
  return (ref, params) => {
    const r: MessageRef = typeof ref === "string" ? { key: ref, ...(params === undefined ? {} : { params }) } : ref;
    const template = table[r.key];
    return template === undefined ? r.key : formatMessage(template, { ...r.params, ...params });
  };
}
