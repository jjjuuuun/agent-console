/** 다른 화면과의 연결 문구(리소스 `wiki-ref` 위젯·실행 상세 칩·메모리 [위키에 올리기]). 위키 이름·동작 이름은 서버 데이터라 여기 없다. */
export const wikiLinkMessages = {
  widget: {
    placeholder: "위키 id",
    listLabel: "위키 목록",
    libraryNote: "위키는 프로젝트에 있습니다. 위키 id가 가져간 프로젝트의 위키 id와 같아야 합니다.",
    suggestGroup: (project: string) => `현재 프로젝트 ‘${project}’의 위키`,
    suggestions: (project: string, ids: readonly string[]) => `현재 프로젝트 ‘${project}’의 위키: ${ids.join(", ")}`,
    loadFailed: "위키 목록을 불러오지 못해 id를 직접 입력합니다.",
    option: (name: string, id: string) => (name === "" || name === id ? id : `${name} (${id})`),
  },
  runChanges: {
    label: "고친 위키 페이지",
    chip: (n: string) => `고친 위키 페이지 ${n}`,
    tip: "이 실행이 위키에 쓴 페이지 보기",
    listLabel: "이 실행이 고친 위키 페이지",
    deletedTip: "지워진 페이지 — 기록에서 되돌릴 수 있습니다",
    open: (wiki: string, path: string) => `${wiki} ${path} 열기`,
  },
  fromMemory: {
    menu: "위키에 올리기…",
    noWiki: "이 프로젝트에 위키가 없습니다. 위키 화면에서 먼저 만드세요.",
    note: "메모리 항목의 복사본으로 만듭니다. 메모리 항목과 연결되지 않습니다.",
    wiki: "올릴 위키",
    loadFailed: "메모리 항목을 읽지 못했습니다",
    created: "위키 페이지를 만들었습니다",
    open: "열기",
  },
} as const;
