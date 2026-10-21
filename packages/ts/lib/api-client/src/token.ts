/** 토큰 값 또는 호출 때마다 최신 값을 돌려주는 함수(부트스트랩 후 갱신 등). */
export type TokenSource = string | (() => string | undefined);

export function resolveToken(source: TokenSource | undefined): string | undefined {
  return typeof source === "function" ? source() : source;
}
