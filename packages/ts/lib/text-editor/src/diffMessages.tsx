import { createContext, type ReactNode } from "react";

export interface TextDiffMessages {
  /** 접힌 구간 안내. `$`는 줄 수로 바뀐다. 예: "변경 없는 $줄 — 펼치기" */
  unchangedLines: string;
  /** 도구 줄의 보기 전환 라벨 */
  split: string;
  unified: string;
  /** 도구 줄 접근성 이름 */
  toolbar: string;
  /** 나란히 보기에서 왼쪽·오른쪽 편집기의 접근성 이름 뒤에 붙는 말 */
  before: string;
  after: string;
}

export const TextDiffMessagesContext = createContext<Partial<TextDiffMessages>>({});

/**
 * 아래 모든 `TextDiff`의 기본 문구를 한 곳에서 주입한다(앱 루트에서 한 번). 개별 `messages` prop이 우선한다.
 * 패키지 기본 문구는 영어이므로 소비 앱은 자기 언어의 문구를 이 공급자로 넣는다.
 */
export function TextDiffMessagesProvider({ messages, children }: { messages: Partial<TextDiffMessages>; children: ReactNode }) {
  return <TextDiffMessagesContext.Provider value={messages}>{children}</TextDiffMessagesContext.Provider>;
}
