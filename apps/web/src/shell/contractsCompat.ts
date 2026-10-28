/**
 * 서버·웹 계약 버전 호환 판정(5.7R.36). 사내 의존 범위 규칙(`^x.y.z`, Python `>=x.y,<x.(y+1)`)과 같은 기준이다:
 * 1.0 이상은 major가 같으면 호환, 0.x는 minor까지 같으면 호환(패치 차이는 하위 호환 추가만).
 * 해석할 수 없는 값은 문자열이 정확히 같을 때만 호환으로 본다.
 */
export type ContractsCompat =
  | { readonly compatible: true }
  | {
      readonly compatible: false;
      /** 더 낮은 쪽. 해석할 수 없으면 null(어느 쪽이 낡았는지 모름). */
      readonly older: "server" | "web" | null;
    };

function parse(version: string): readonly [number, number, number] | null {
  const m = /^(\d+)\.(\d+)\.(\d+)/.exec(version.trim());
  return m ? [Number(m[1]), Number(m[2]), Number(m[3])] : null;
}

function compare(a: readonly number[], b: readonly number[]): number {
  for (let i = 0; i < a.length; i += 1) {
    const d = (a[i] ?? 0) - (b[i] ?? 0);
    if (d !== 0) return d;
  }
  return 0;
}

/**
 * 서버가 보고한 계약 버전과 웹 번들의 계약 버전을 비교한다.
 *
 * @param server 서버 `/bootstrap`의 `contracts_version`. 빈 문자열이면 비교하지 않는다(호환으로 본다).
 * @param web 웹이 빌드된 `CONTRACTS_VERSION`.
 * @returns 호환 여부와, 호환되지 않으면 더 낮은(낡은) 쪽.
 */
export function contractsCompat(server: string, web: string): ContractsCompat {
  if (server === "" || server === web) return { compatible: true };
  const s = parse(server);
  const w = parse(web);
  if (!s || !w) return { compatible: false, older: null };
  const sameLine = s[0] === w[0] && (s[0] > 0 || s[1] === w[1]);
  if (sameLine) return { compatible: true };
  return { compatible: false, older: compare(s, w) < 0 ? "server" : "web" };
}
