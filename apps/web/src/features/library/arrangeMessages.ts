/** 목록 보기(묶기·정렬·접기)·폴더 이동·라벨 편집의 공용 문구. 화면별 기준 이름은 `groupNames` 등에 덧붙여 쓴다(5.2R.62·63). */
export const arrangeMessages = {
  viewLabel: "보기",
  groupTitle: "묶는 기준",
  sortTitle: "정렬",
  collapseAll: "모두 접기",
  expandAll: "모두 펼치기",
  none: "묶지 않음",
  groupNames: { "group.folder": "폴더", "group.labels": "라벨", "group.project": "프로젝트", "group.type": "종류", "group.attribute": "속성 키…" } as Record<string, string>,
  summaryGroup: (name: string) => `${name}별`,
  noneLabels: { "group.folder": "(폴더 없음)", "group.labels": "(라벨 없음)", "group.project": "(공용)", "group.type": "(종류 없음)", "group.attribute": "(값 없음)" } as Record<string, string>,
  sortNames: { "sort.name": "이름", "sort.modified": "최근 수정" } as Record<string, string>,
  /** 보기 버튼 글자에 쓰는 정렬 이름 */
  sortSummaries: { "sort.name": "이름순", "sort.modified": "최근 수정순" } as Record<string, string>,
  /** 저장 중 버전이 어긋났을 때(412·428) 안내와 다시 시도 */
  conflict: "다른 곳에서 먼저 바뀌어 저장하지 못했습니다. 다시 시도하면 최신 내용에 적용합니다.",
  retry: "다시 시도",
  noProjects: "프로젝트에 속한 항목이 없습니다",
  attrKey: "속성 키",
  attrKeyPlaceholder: "예: team_tag",
  move: {
    title: "폴더로 이동",
    target: (name: string) => `‘${name}’을(를) 옮길 폴더`,
    search: "폴더 찾기 또는 새 이름 입력",
    listLabel: "폴더 목록",
    create: (name: string) => `+ 새 폴더 "${name}" 만들기`,
    clear: "폴더 없음으로",
    current: "현재",
    cancel: "취소",
    done: (name: string, folder: string) => `‘${name}’을(를) ‘${folder}’ 폴더로 옮겼습니다`,
    doneClear: (name: string) => `‘${name}’을(를) 폴더 밖으로 옮겼습니다`,
    undo: "되돌리기",
    undone: "되돌렸습니다",
    failed: "폴더를 옮기지 못했습니다",
  },
  labels: {
    title: "라벨 편집",
    target: (name: string) => `‘${name}’의 라벨`,
    input: "라벨 추가(Enter)",
    remove: (l: string) => `라벨 ${l} 삭제`,
    empty: "라벨이 없습니다",
    save: "저장",
    cancel: "취소",
    saved: (name: string) => `‘${name}’의 라벨을 저장했습니다`,
    failed: "라벨을 저장하지 못했습니다",
  },
};

export type ArrangeMessages = typeof arrangeMessages;
