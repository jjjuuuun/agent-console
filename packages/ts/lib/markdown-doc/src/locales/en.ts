import { type MarkdownDocMessages, type MessageTree, flattenMessageTree } from "../messages";
import json from "./en.json";

/** 문구 묶음(`en`). 컴포넌트의 `messages` 인자에 그대로 넘긴다. */
export const en = flattenMessageTree(json) as MarkdownDocMessages;
/** 같은 문구의 나무 모양(`en.json` 그대로). i18next 같은 나무 묶음을 받는 쪽에서 쓴다. */
export const tree: MessageTree = json;
export default en;
