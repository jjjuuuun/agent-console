import { useT } from "@agent-console/i18n";
import { createToastText } from "../../app/ToastText";
import { useViewMessages } from "./format";

/** 메모리 화면 알림이 쓰는 문구 도구: 현재 언어의 `memory` 번역 함수와 보기 문구 표. */
function useMemoryToastTools() {
  return { t: useT("memory"), view: useViewMessages() };
}

/** 메모리 화면 알림 글: 그릴 때 현재 언어로 만든다(떠 있는 알림도 언어를 따른다). */
export const MemoryToast = createToastText(useMemoryToastTools);
