import { BACKEND_READINESS_ANCHOR } from "../backendReadiness";

/** 공통 설정 섹션 id(설정 화면 섹션 정의의 `common`). 앵커 주소를 만들 때만 쓴다. */
const COMMON_SECTION_ID = "common";

/**
 * 설정 › 에이전트 기본값의 "백엔드 로그인·준비 상태" 칸으로 가는 주소 해시.
 * 섹션 id 뒤 `/앵커`는 설정 화면이 섹션 선택에는 무시하고, 준비 상태 섹션이 보면 그 제목으로 스크롤하고 초점을 준다.
 */
export const SETTINGS_BACKEND_READINESS_HASH = `#${COMMON_SECTION_ID}/${BACKEND_READINESS_ANCHOR}`;
