import type { ComposerMessages } from "../composer/Composer";
import type { InteractionMessages } from "../interaction/messages";
import type { ChatMessages } from "../messages/messages";

/** 채팅 패키지 문구 묶음 한 언어분. 컴포넌트마다 `messages` prop이 따로이므로 묶음 이름으로 나눠 넘긴다. */
export interface ChatLocale {
  /** `MessageList`·`TurnView`·`ReplyGroup`·`ProgressStrip`의 `messages` */
  chat: ChatMessages;
  /** `InteractionCard`의 `messages` */
  interaction: InteractionMessages;
  /** `Composer`의 `messages` */
  composer: ComposerMessages;
  /** `Markdown`의 `messages` */
  markdown: { copy: string; copied: string };
}
