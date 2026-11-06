/**
 * 문구 표. 앱이 `messages` prop으로 일부만 덮어쓴다(번역·용어 바꾸기).
 * `source.<출처>` 같은 키는 열린 문자열 계약 값에 붙이는 선택 문구이고, 표에 없으면 값 원문을 보인다.
 */
export const defaultMessages = {
  "common.close": "닫기",
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
  "editor.issue.line": "{line}번째 줄",
  "source.label": "출처: {source}",
  "source.tip": "이 값이 어디에서 왔는지",
} as const;

export type MarkdownDocMessageKey = keyof typeof defaultMessages;
/** 문구 표. 기본 키는 모두 있고 앱이 더한 키도 허용한다. */
export type MarkdownDocMessages = { [K in MarkdownDocMessageKey]: string } & Readonly<Record<string, string>>;

/** 틀의 `{이름}` 자리를 값으로 바꾼다. 없는 이름은 그대로 둔다. */
export function formatMessage(template: string, vars: Readonly<Record<string, string | number>> = {}): string {
  return template.replace(/\{(\w+)\}/g, (m, k: string) => (k in vars ? String(vars[k]) : m));
}

/** 부분 문구 표를 기본 문구와 합친다. */
export function resolveMessages(partial?: Readonly<Record<string, string>>): MarkdownDocMessages {
  return partial ? ({ ...defaultMessages, ...partial } as MarkdownDocMessages) : (defaultMessages as MarkdownDocMessages);
}

/** 키로 문구를 찾는다. 없으면 `fallback`(보통 모르는 계약 어휘 원문). */
export function messageOr(messages: Readonly<Record<string, string>>, key: string, fallback: string): string {
  return messages[key] ?? fallback;
}
