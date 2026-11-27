import { createToastText } from "../../app/ToastText";
import { useTeamMessages } from "./messages";

/** 팀 화면 알림 글: 그릴 때 현재 언어의 `teams` 표로 만든다(떠 있는 알림도 언어를 따른다). */
export const TeamToast = createToastText(useTeamMessages);

/** `TeamToast`의 `render`가 받는 문구 표 */
export type TeamToastMessages = ReturnType<typeof useTeamMessages>;
