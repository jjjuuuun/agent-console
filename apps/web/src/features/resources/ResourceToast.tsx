import { createToastText } from "../../app/ToastText";
import { useResourceMessages } from "./messages";

/** 리소스 화면 알림 글: 그릴 때 현재 언어의 `resources` 표로 만든다(떠 있는 알림도 언어를 따른다). */
export const ResourceToast = createToastText(useResourceMessages);
