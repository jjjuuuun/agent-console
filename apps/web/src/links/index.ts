/**
 * 두 기능 이상을 함께 쓰는 연결 층. 기능 폴더(`features/*`)는 이 폴더를 import하지 않는다
 * (dependency-cruiser `web-features-use-links-folder`). 여기에는 연동 부분 등록 데이터와,
 * 두 기능의 공개 API를 조립하는 컴포넌트(`links/<a>-<b>/`)를 둔다.
 */
export { DEFAULT_LINK_PARTS } from "./linkParts";
export { DEFAULT_CONFIG_WIDGETS } from "./configWidgets";
