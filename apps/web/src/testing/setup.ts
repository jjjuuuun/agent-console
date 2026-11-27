// web 테스트 공통 설정(루트 vitest.config.ts의 web 프로젝트 setupFiles).
// 앱 전체를 띄우는 화면 테스트는 부하가 큰 환경(CI 러너·동시 실행)에서 Testing Library 기본 대기 1초를 넘길 수 있다.
// 대기 상한만 늘린다(조건이 먼저 맞으면 바로 끝나므로 통과하는 테스트는 느려지지 않는다).
import { configure } from "@testing-library/react";

configure({ asyncUtilTimeout: 10_000 });

// 화면 언어는 ko로 고정한다(기존 한국어 단언 유지, design §I18N.5). 앱은 저장된 언어가 없으면 브라우저 언어를 따르므로 브라우저 언어를 ko로 둔다.
Object.defineProperty(globalThis.navigator, "languages", { value: ["ko-KR", "ko"], configurable: true });
Object.defineProperty(globalThis.navigator, "language", { value: "ko-KR", configurable: true });

// `<html lang>`은 앱 루트와 언어 컨트롤러가 화면 언어에 맞춰 쓴다(화면의 서식은 `useFormat()`이 언어 코드로 직접 읽고 이 속성을 읽지 않는다).
// 앱 밖에서 그리는 테스트(접근성·스크린리더 검사)도 한국어 문서로 보이도록 초기값만 둔다.
if (typeof document !== "undefined") document.documentElement.lang = "ko";
