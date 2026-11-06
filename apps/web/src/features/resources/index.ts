/** 리소스 폼의 공개 API: 다른 기능(팀 편집기의 만들기 서랍)이 리소스 화면과 같은 편집기·만들기 로직을 쓴다. 화면(`ResourcesScreen`)은 라우트에서 직접 import한다. */
export { ResourceEditorForm, type ResourceEditorFormProps, type ResourceDocUpdate } from "./ResourceEditorForm";
export { ResourceCreateForm, useResourceCreateDraft, type ResourceCreateDraft, type ResourceCreateFormProps } from "./ResourceCreateForm";
export { createResourceDoc, type CreateResourceOutcome } from "./resourceLogic";
/** 여러 파일 편집(파일 트리 + 편집기)과 그 초안 로직: 리소스가 아닌 다중 파일 본문(예: 문서 틀 뼈대 파일)도 같은 편집기를 쓴다. */
export { MultiFileTab, type MultiFileTabProps } from "./MultiFileTab";
export { planFileChanges, sortEntries, type FileEntry, type FilePlan } from "./fileTreeLogic";
