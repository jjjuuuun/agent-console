/** 정의 목록·상세 화면(팀 구성·에이전트·리소스)이 함께 쓰는 문구. */
export const libraryMessages = {
  create: "만들기",
  cancel: "취소",
  close: "닫기",
  retry: "다시 시도",
  copy: "복사",
  copied: "복사했습니다",
  more: "더 보기",
  rowMenu: "행 메뉴",
  detailMenu: "더 많은 동작",
  search: "검색",
  loading: "불러오는 중…",
  none: "없음",
  newDialog: {
    name: "이름",
    id: "id",
    idHint: "파일 이름이 됩니다. 영숫자·하이픈·밑줄·점만 쓸 수 있고 나중에 바꿀 수 없습니다.",
    description: "설명",
    idErrors: {
      empty: "id를 입력하세요",
      pattern: "영숫자로 시작하고 영숫자·하이픈·밑줄·점만 쓸 수 있습니다",
      duplicate: "이미 있는 id입니다",
    },
    nameRequired: "이름을 입력하세요",
  },
  delete: {
    title: (name: string) => `‘${name}’을(를) 삭제할까요?`,
    body: "삭제한 뒤에는 되돌릴 수 없습니다.",
    action: "삭제",
    usedBy: (n: number) => `이 항목을 쓰는 곳 ${n}개`,
    understood: "이해했습니다",
    failed: "삭제하지 못했습니다",
  },
  picker: {
    title: "리소스 붙이기",
    search: "이름·설명으로 찾기",
    allTypes: "전체",
    empty: "붙일 수 있는 리소스가 없습니다",
    noMatch: "일치하는 리소스가 없습니다",
    createNew: "새 리소스 만들기 →",
    pick: (name: string) => `${name} 붙이기`,
  },
  attach: {
    moveUp: "위로 이동",
    moveDown: "아래로 이동",
    remove: "제거",
    modeLabel: "붙이는 방식",
    add: "+ 리소스 붙이기",
    empty: "붙은 리소스가 없습니다",
    readOnly: "읽기 전용",
    missing: "(찾을 수 없음)",
    modes: { add: "추가", replace: "대체", remove: "제외" } as Record<string, string>,
  },
  usage: {
    kindTeam: "팀 구성",
    kindAgent: "에이전트",
    kindResource: "리소스",
    kindCommon: "공통",
    nodes: (labels: string) => `노드 ${labels}`,
    layer: "붙은 층",
  },
  menu: { label: "메뉴" },
  agentForm: {
    customModel: "직접 입력",
    modelsFailed: "모델 목록을 불러오지 못했습니다. 직접 입력할 수 있습니다.",
    addTag: "항목 추가",
    removeTag: (tag: string) => `${tag} 제거`,
  },
  avatarLabel: (name: string) => `${name} 아이콘`,
} as const;

/** 첨부 방식 라벨. 모르는 값은 서버 문자열 그대로. */
export function modeLabel(mode: string): string {
  return libraryMessages.attach.modes[mode] ?? mode;
}
