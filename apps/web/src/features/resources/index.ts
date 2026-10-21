/** 리소스 폼의 공개 API: 다른 기능(팀 편집기의 만들기 서랍)이 리소스 화면과 같은 편집기·만들기 로직을 쓴다. 화면(`ResourcesScreen`)은 라우트에서 직접 import한다. */
export { ResourceEditorForm, type ResourceEditorFormProps, type ResourceDocUpdate } from "./ResourceEditorForm";
export { ResourceCreateForm, useResourceCreateDraft, type ResourceCreateDraft, type ResourceCreateFormProps } from "./ResourceCreateForm";
export { createResourceDoc, type CreateResourceOutcome } from "./resourceLogic";
