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
