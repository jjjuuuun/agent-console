import json from "./en.json";
import type { GraphEditorLocale } from "./types";

/** 문구 묶음(`en`): `messages`는 `GraphEditor`의 `messages`로, `shapes`는 `localizeEdgeShapes`로, `layout`은 `createElkEngine`으로 넘긴다. */
export const en: GraphEditorLocale = json;
export default en;
