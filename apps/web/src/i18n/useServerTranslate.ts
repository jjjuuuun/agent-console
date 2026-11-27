import { useServerText, type TextTemplateLike } from "@agent-console/i18n";
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

/** 서버 글자 칸을 그리는 함수: `(칸 값, 그 칸의 text_templates 항목)`. 틀이 있고 모두 번역되면 번역한 틀을 값으로 채운 문장이다. */
export type ServerRender = (value: string, parts?: readonly TextTemplateLike[] | null) => string;

/**
 * `text_templates`를 가진 서버 응답(준비 상태·연결 테스트·로그인·로그아웃·로그 이벤트)의 글자 칸을 그리는 함수(I.12e).
 * 앱 i18n 공급자 밖이면 칸 값을 그대로 돌려준다.
 */
export function useServerRender(): ServerRender {
  const server = useServerText();
  const inProvider = useOptionalI18n() !== null;
  return inProvider ? server.render : (value) => value;
}
