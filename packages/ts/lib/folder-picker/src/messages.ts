/**
 * folder-picker 문구(docs/design/screen-projects.md §12.1, 접두 없이 원래 키 그대로). 값의 `{이름}`은 자리표시자다.
 * 모듈·기능 이름은 문구에 없다. 앱은 `messages` prop으로 일부만 덮어쓸 수 있다.
 */
export const defaultMessages = {
  "folder.path.label": "프로젝트 폴더",
  "folder.path.input_label": "폴더 경로",
  "folder.path.placeholder": "서버 컴퓨터의 폴더 경로",
  "folder.path.help": "서버가 실행 중인 컴퓨터의 폴더입니다. 경로를 붙여 넣으세요.",
  "folder.path.manual": "경로를 직접 입력",
  "folder.pick.empty": "선택한 폴더가 여기에 표시됩니다",
  "folder.pick.selected": "선택한 폴더",
  "folder.pick.copy": "경로 복사",
  "folder.pick.copy_short": "복사",
  "folder.pick.copied": "복사됨",
  "folder.pick.action": "폴더 선택…",
  "folder.pick.again": "다른 폴더 선택…",
  "folder.pick.retry": "다시 선택",
  "folder.pick.waiting": "폴더 선택 창에서 고르세요…",
  "folder.pick.cancel": "선택 취소",
  "folder.pick.waiting_hint": "창이 보이지 않으면 작업 표시줄이나 이 브라우저 창 뒤를 확인하세요.",
  "folder.pick.cancelled": "선택을 취소했습니다",
  "folder.pick.use_browser": "앱 안에서 찾아보기",
  "folder.pick.unavailable": "이 컴퓨터에서 폴더 선택 창을 쓸 수 없어 앱 안 찾아보기를 엽니다.",
  "folder.pick.failed": "폴더 선택 창을 열지 못했습니다. 앱 안 찾아보기를 엽니다.",
  "folder.pick.busy": "다른 폴더 선택 창이 이미 열려 있습니다. 그 창에서 고르거나 닫은 뒤 다시 시도하세요.",
  "folder.pick.timeout": "선택 시간이 지나 창을 닫았습니다.",
  "folder.pick.reason": "자세히",
  "folder.browse.open": "찾아보기…",
  "folder.browse.close": "찾아보기 접기",
  "folder.browse.roots": "시작 위치",
  "folder.browse.breadcrumb": "경로",
  "folder.browse.breadcrumb_more": "중간 경로 더 보기",
  "folder.browse.list": "폴더 목록",
  "folder.browse.hidden": "숨김 폴더 보기",
  "folder.browse.new": "새 폴더",
  "folder.browse.new_name": "새 폴더 이름",
  "folder.browse.hint": "현재 위치가 입력 칸에 들어갑니다.",
  "folder.browse.select": "이 폴더 선택",
  "folder.browse.empty": "하위 폴더가 없습니다",
  "folder.browse.loading": "폴더 목록을 불러오는 중…",
  "folder.browse.truncated": "항목이 많아 앞의 {n}개만 보입니다. 경로를 직접 입력하면 좁힐 수 있습니다.",
  "folder.browse.error": "폴더 목록을 불러오지 못했습니다",
  "folder.browse.retry": "다시 시도",
  "folder.browse.registered": "등록됨: {name}",
  "folder.browse.locked": "읽을 수 없는 폴더입니다",
  "folder.browse.link": "링크 — 실제 경로로 저장됩니다",
  "folder.browse.remote_disabled": "서버가 이 컴퓨터 밖에서 접속할 수 있게 열려 있어 폴더 찾아보기를 쓸 수 없습니다. 경로를 직접 입력하세요.",
  "folder.new.error.exists": "이미 있는 이름입니다",
  "folder.new.error.invalid": "폴더 이름에 쓸 수 없는 글자가 있습니다",
  "folder.new.error.failed": "폴더를 만들지 못했습니다",
  "folder.check.checking": "확인하는 중…",
  "folder.check.ok": "사용할 수 있는 폴더입니다.",
  "folder.check.saved_as": "저장될 경로",
  "folder.check.saved_as_diff": "입력한 경로는 {path}로 저장됩니다.",
  "folder.check.readonly": "쓰기 권한이 없습니다. 이 폴더에서 에이전트가 파일을 쓰는 실행 작업은 실패할 수 있습니다.",
  // `{dir}`(앱이 `configDir`로 준 폴더 이름)는 고정폭 글자로 그려진다. `configDir`가 없으면 위 문구를 쓴다.
  "folder.check.readonly_config": "이 폴더에 {dir} 폴더를 만들 수 없어 구성을 가져오거나 고칠 수 없습니다(보기·로그는 됩니다). 에이전트가 이 폴더에 파일을 쓰는 작업도 실패할 수 있습니다.",
  "folder.check.creates_dir": "이 폴더에 {dir} 폴더를 만들어 프로젝트 구성과 메모리를 저장합니다. 폴더의 다른 파일은 바꾸지 않습니다.",
  "folder.check.manifest_found": "이 폴더에 프로젝트 구성이 이미 있습니다{detail}. 그대로 불러옵니다.",
  "folder.check.manifest_detail_name": ": ‘{name}’",
  "folder.check.manifest_detail_count": " · 구성 {n}개",
  "folder.check.manifest_invalid": "이 폴더의 프로젝트 설정 파일을 읽을 수 없습니다. 추가하면 ‘설정 파일 오류’ 상태로 시작합니다.",
  "folder.check.missing": "폴더가 없습니다. 만들까요?",
  "folder.check.create": "이 경로에 폴더 만들기",
  "folder.check.creating": "만드는 중…",
  "folder.check.missing_parent": "상위 폴더가 없어 만들 수 없습니다. 존재하는 상위 폴더를 고르세요.",
  "folder.check.not_directory": "폴더가 아니라 파일입니다. 폴더를 고르세요.",
  "folder.check.no_access": "이 폴더를 읽을 수 없습니다(권한). 서버를 실행한 계정이 접근할 수 있는 폴더를 고르세요.",
  "folder.check.taken": "이미 ‘{name}’ 프로젝트로 등록된 폴더입니다.",
  "folder.check.taken_open": "열기",
  "folder.check.taken_archived": "‘{name}’으로 등록했다가 해제한 폴더입니다. 이전 기록을 이어서 쓸 수 있습니다.",
  "folder.check.overlap_parent": "이 폴더를 포함하는 ‘{name}’({path}) 프로젝트가 이미 있습니다.",
  "folder.check.overlap_child": "이 폴더 안에 이미 등록된 ‘{name}’({path}) 프로젝트가 있습니다. 상위 폴더를 등록하려면 먼저 그 프로젝트의 등록을 해제하세요.",
  "folder.check.overlap_open": "그 프로젝트 열기",
  "folder.check.overlap_why": "한 경로가 두 프로젝트에 속하면 로그·실행 기록이 섞이기 때문에 겹치는 폴더는 따로 등록할 수 없습니다.",
  "folder.check.remote_disabled": "서버가 이 컴퓨터 밖에서 접속할 수 있게 열려 있어 폴더를 확인할 수 없습니다. 경로를 확인하지 않고 추가하면 서버가 거부할 수 있습니다.",
  "folder.check.error": "폴더를 확인하지 못했습니다.",
  "folder.check.recheck": "다시 확인",
  "folder.check.same_path": "이전 경로와 같습니다. 폴더가 다시 생겼다면 [다시 확인]을 쓰세요.",
  "folder.check.nearest_note": "입력한 경로가 없어 가장 가까운 상위 폴더({path})에서 찾아보기를 시작합니다.",
  // 명세 표에 없는 보충(입력 문제 이유). 서버 `problem` 값별 문구, 모르는 값은 invalid.
  "folder.check.invalid": "쓸 수 없는 경로입니다.",
  "folder.check.invalid.relative": "절대 경로를 입력하세요.",
  "folder.check.invalid.foreign_path": "이 서버에서 쓸 수 없는 형식의 경로입니다.",
  "folder.check.invalid.no_home": "홈 폴더를 알 수 없어 ~ 를 풀 수 없습니다.",
  "folder.check.invalid.outside_roots": "서버가 허용한 탐색 범위 밖의 경로입니다.",
  "folder.check.invalid.invalid_path": "경로에 쓸 수 없는 글자가 있습니다.",
} as const;

export type MessageKey = keyof typeof defaultMessages;
export type FolderPickerMessages = Record<MessageKey, string>;
export type MessageOverrides = Partial<Record<string, string>>;
export type Translate = (key: MessageKey | (string & {}), vars?: Record<string, string | number>) => string;

/** `{이름}` 자리표시자를 채운다. 없는 값은 그대로 둔다. */
export function formatMessage(template: string, vars?: Record<string, string | number>): string {
  if (!vars) return template;
  return template.replace(/\{([A-Za-z0-9_]+)\}/g, (whole, name: string) => (name in vars ? String(vars[name]) : whole));
}

/** 기본 문구 위에 덮어쓸 문구를 얹은 번역 함수를 만든다. 키가 없으면 키 문자열을 돌려준다. */
export function createTranslate(overrides?: MessageOverrides): Translate {
  const table: Record<string, string | undefined> = { ...defaultMessages, ...overrides };
  return (key, vars) => formatMessage(table[key] ?? key, vars);
}
