import { useServerText } from "@agent-console/i18n";
import { useOptionalI18n } from "./AppI18n";

const identity = (text: string): string => text;

/**
 * 서버 원문(스키마 제목·설명·enum 라벨 같은 글자)을 현재 화면 언어로 바꾸는 함수.
 * 앱 i18n 공급자 밖(단독 테스트 등)이면 원문을 그대로 돌려준다. 언어나 서버 묶음이 바뀌면 새 함수가 되어 다시 그려진다.
 */
export function useServerTranslate(): (text: string) => string {
  const server = useServerText();
  const inProvider = useOptionalI18n() !== null;
  return inProvider ? server.text : identity;
}
