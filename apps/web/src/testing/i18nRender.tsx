import { koI18n } from "./koText";

/** 컴포넌트 테스트용 render(I.12a의 `renderI18n.tsx`와 같다: 한국어 앱 묶음 공급자로 감싼다). 옛 import 경로를 위해 다시 내보낸다. */
export { render } from "./renderI18n";

/** 한국어 앱 묶음 전체를 실은 i18n 인스턴스(`koText.ts`의 `koI18n`). */
export const createKoTestI18n = () => koI18n;
