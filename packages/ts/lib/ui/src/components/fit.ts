/**
 * 한 줄에 다 안 들어가는 항목을 숨길 때 보일 항목을 고르는 순수 함수.
 *
 * @param widths 항목 폭(원래 순서)
 * @param gap 항목 사이 간격(px)
 * @param available 줄 전체 폭(px). 0 이하이면 레이아웃을 알 수 없다고 보고 모두 보인다.
 * @param moreWidth "더 보기"/`+N` 버튼 폭(px). 숨길 항목이 있을 때만 차지한다.
 * @param priority 반드시 보여야 하는 항목 인덱스(활성·선택). 폭이 모자라도 보인다.
 * @returns 보이는 항목 인덱스 집합(원래 순서는 호출자가 유지한다)
 */
export function computeVisible(widths: readonly number[], gap: number, available: number, moreWidth: number, priority: readonly number[] = []): Set<number> {
  const all = new Set(widths.keys());
  if (available <= 0 || widths.length === 0) return all;
  const total = widths.reduce((sum, w) => sum + w, 0) + gap * (widths.length - 1);
  if (total <= available) return all;
  const room = available - moreWidth - gap;
  const visible = new Set<number>();
  let used = 0;
  const take = (index: number, force: boolean): boolean => {
    const w = widths[index];
    if (w === undefined || visible.has(index)) return true;
    const next = used + (visible.size > 0 ? gap : 0) + w;
    if (!force && next > room) return false;
    visible.add(index);
    used = next;
    return true;
  };
  for (const index of priority) take(index, true);
  // 우선 항목 뒤에 원래 순서대로 들어가는 만큼 채운다(들어가지 않는 항목에서 멈춘다: 순서 건너뛰기 없음).
  for (let i = 0; i < widths.length; i++) {
    if (visible.has(i)) continue;
    if (!take(i, false)) break;
  }
  return visible;
}
