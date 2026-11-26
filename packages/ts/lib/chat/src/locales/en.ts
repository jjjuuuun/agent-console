import json from "./en.json";
import type { ChatLocale } from "./types";

/** 문구 묶음(`en`): `chat`·`interaction`·`composer`·`markdown`을 각 컴포넌트의 `messages`로 넘긴다. */
export const en: ChatLocale = json;
export default en;
