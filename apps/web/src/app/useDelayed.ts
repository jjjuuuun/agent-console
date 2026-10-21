import { useEffect, useState } from "react";

/** `flag`가 `ms` 이상 계속 true일 때만 true(짧은 로딩에서 스피너가 깜박이지 않게). */
export function useDelayed(flag: boolean, ms = 200): boolean {
  const [shown, setShown] = useState(false);
  useEffect(() => {
    if (!flag) return;
    const handle = setTimeout(() => setShown(true), ms);
    return () => {
      clearTimeout(handle);
      setShown(false);
    };
  }, [flag, ms]);
  return flag && shown;
}
