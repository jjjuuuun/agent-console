import { useLookupMessage } from "../../app/shellMessages";
import { createToastText } from "../../app/ToastText";
import { useFolderHomeMessages } from "./folderHomeMessages";
import { useProjectMessages } from "./messages";
import { useProjectsText } from "./projectsText";
import { useScopeMessages } from "./scopeMessages";

/** 폴더·프로젝트 홈 알림 글: 그릴 때 현재 언어의 `folderHome` 표로 만든다(떠 있는 알림도 언어를 따른다). */
export const FolderHomeToast = createToastText(useFolderHomeMessages);
/** 프로젝트 전환기 알림 글. */
export const ProjectToast = createToastText(useProjectMessages);
/** 프로젝트 설정 구역 알림 글: 범위 문구 표와 화면 이름 조회 함수를 함께 준다. */
function useScopeToastTools() {
  return { scope: useScopeMessages(), lookup: useLookupMessage() };
}
export const ScopeToast = createToastText(useScopeToastTools);
/** 프로젝트 번역 함수(`text(key, params)`)로 만드는 알림 글. */
export const ProjectsTextToast = createToastText(useProjectsText);
