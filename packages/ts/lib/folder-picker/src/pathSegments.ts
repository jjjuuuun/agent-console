/** 절대 경로를 빵부스러기 조각으로 나눈다. 구분자는 경로에 처음 나오는 `/` 또는 `\`. */
export interface PathSegment {
  label: string;
  /** 이 조각까지의 경로. */
  path: string;
}

export function splitPath(path: string): PathSegment[] {
  const m = /[\\/]/.exec(path);
  if (!m) return path ? [{ label: path, path }] : [];
  const sep = m[0];
  const parts = path.split(sep);
  const out: PathSegment[] = [];
  let acc = "";
  parts.forEach((part, i) => {
    if (i === 0) {
      if (part === "") {
        out.push({ label: sep, path: sep });
        acc = "";
        return;
      }
      acc = part;
      // 드라이브(`C:`)는 `C:\` 로 연다.
      out.push({ label: part, path: /^[A-Za-z]:$/.test(part) ? part + sep : part });
      return;
    }
    if (part === "") return;
    acc = acc === "" ? sep + part : acc.endsWith(sep) ? acc + part : acc + sep + part;
    out.push({ label: part, path: acc });
  });
  return out;
}

/**
 * 빵부스러기가 `budgetCells`칸을 넘으면 가운데 조각들을 접는다(처음 1개·마지막 2개는 남김).
 * 돌려주는 `hidden`은 접힌 조각, `shown`은 `…` 앞뒤로 보일 조각이다.
 */
export function collapseCrumbs<T extends { label: string }>(
  items: readonly T[],
  budgetCells: number,
  widthOf: (label: string) => number,
): { head: T[]; hidden: T[]; tail: T[] } {
  const total = items.reduce((n, it) => n + widthOf(it.label) + 2, 0);
  if (total <= budgetCells || items.length <= 4) return { head: [...items], hidden: [], tail: [] };
  return { head: items.slice(0, 1), hidden: items.slice(1, items.length - 2), tail: items.slice(items.length - 2) };
}
