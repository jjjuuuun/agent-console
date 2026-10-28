import { useEffect, useState } from "react";

/** `active`가 true가 된 지 `ms` 지난 뒤에만 true(깜빡임 방지용 지연 표시). `ms`가 0 이하면 `active` 그대로. */
export function useAfter(active: boolean, ms: number): boolean {
  const [on, setOn] = useState(false);
  useEffect(() => {
    if (!active || ms <= 0) return;
    const h = setTimeout(() => setOn(true), ms);
    return () => {
      clearTimeout(h);
      setOn(false);
    };
  }, [active, ms]);
  return ms <= 0 ? active : active && on;
}
