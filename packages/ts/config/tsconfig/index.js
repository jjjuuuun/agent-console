import { fileURLToPath } from "node:url";

/**
 * 이 패키지가 싣고 있는 설정 파일의 절대 경로를 돌려준다.
 * @param {string} name 확장자를 뺀 파일 이름(예: `base`)
 * @returns {string}
 */
export function configPath(name) {
  return fileURLToPath(new URL(`./${name}.json`, import.meta.url));
}
