// web 테스트 공통 설정(루트 vitest.config.ts의 web 프로젝트 setupFiles).
// 앱 전체를 띄우는 화면 테스트는 부하가 큰 환경(CI 러너·동시 실행)에서 Testing Library 기본 대기 1초를 넘길 수 있다.
// 대기 상한만 늘린다(조건이 먼저 맞으면 바로 끝나므로 통과하는 테스트는 느려지지 않는다).
import { configure } from "@testing-library/react";

configure({ asyncUtilTimeout: 10_000 });
