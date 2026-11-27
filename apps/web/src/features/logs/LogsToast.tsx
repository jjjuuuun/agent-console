import { createToastText } from "../../app/ToastText";
import { useLogsMessages } from "./messages";

/** 로그 화면 알림 글: 그릴 때 현재 언어의 `logs` 표로 만든다(떠 있는 알림도 언어를 따른다). */
export const LogsToast = createToastText(useLogsMessages);
