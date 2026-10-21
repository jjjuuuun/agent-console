export interface RetryFocusOptions {
  /** 포커스를 줄 요소(아직 없으면 null) */
  find(): HTMLElement | null;
  /** 지금 포커스가 이 요소를 가져가도 되는 곳인가(기본: body 또는 캔버스 `.react-flow` 안) */
  stealable?(active: Element | null): boolean;
  intervalMs?: number;
  maxTries?: number;
  /** 테스트에서 문서를 바꿀 때 */
  doc?: Document;
}

const defaultStealable = (active: Element | null): boolean => active === null || active === document.body || active.closest(".react-flow") !== null;

/**
 * 다른 처리(편집기의 선택 포커스 등)가 끝난 뒤에 요소로 포커스를 옮기려고 짧게 다시 시도한다. 취소 함수를 돌려준다.
 * 안전 규칙: 사용자가 눌렀거나(pointerdown·keydown) 포커스가 다른 곳(캔버스·body 밖)에 있으면 즉시 멈추고 되돌리지 않는다.
 * 호출자는 언마운트·재요청 때 취소 함수를 부른다.
 */
export function retryFocus(opts: RetryFocusOptions): () => void {
  const doc = opts.doc ?? document;
  const stealable = opts.stealable ?? defaultStealable;
  const max = opts.maxTries ?? 12;
  let tries = 0;
  let held = 0;
  const stop = () => {
    clearInterval(timer);
    doc.removeEventListener("pointerdown", stop, true);
    doc.removeEventListener("keydown", stop, true);
  };
  const timer = setInterval(() => {
    tries += 1;
    const el = opts.find();
    if (el !== null) {
      if (doc.activeElement === el) held += 1;
      else if (stealable(doc.activeElement)) {
        el.focus();
        held = 0;
      } else {
        stop();
        return;
      }
    }
    if (tries >= max || held >= 3) stop();
  }, opts.intervalMs ?? 120);
  doc.addEventListener("pointerdown", stop, true);
  doc.addEventListener("keydown", stop, true);
  return stop;
}
