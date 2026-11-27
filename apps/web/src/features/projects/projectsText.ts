import { useMemo } from "react";
import { createProjectsText, flattenMessageTree, type MessageTree as ProjectsTree, type ProjectsText } from "@agent-console/projects";
import { useLibMessages, type MessageTree } from "@agent-console/i18n";
// 문구의 모양(키 목록)을 얻으려는 기본 묶음. 화면에 보이는 값은 현재 언어 묶음이 덮어쓴다.
import { tree as baseTree } from "@agent-console/projects/locales/ko";

/** `@agent-console/projects` 문구 변환 함수(상태 이름·막힘 이유·복사 계획·공간 칩 문구)를 현재 화면 언어로 만든다. */
export function useProjectsText(): ProjectsText {
  const tree = useLibMessages("projects", baseTree as unknown as MessageTree);
  return useMemo(() => createProjectsText(flattenMessageTree(tree as unknown as ProjectsTree)), [tree]);
}
