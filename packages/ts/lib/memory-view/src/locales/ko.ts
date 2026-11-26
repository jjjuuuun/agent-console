import { type MessageTree, type MemoryViewMessages, defaultMessages } from "../messages";
import json from "./ko.json";

/** 문구 묶음(`ko`). 컴포넌트·`scopeLabel` 등의 `messages` 인자에 그대로 넘긴다. */
export const ko: MemoryViewMessages = defaultMessages as MemoryViewMessages;
/** 같은 문구의 나무 모양(`ko.json` 그대로). i18next 같은 나무 묶음을 받는 쪽에서 쓴다. */
export const tree: MessageTree = json;
export default ko;
