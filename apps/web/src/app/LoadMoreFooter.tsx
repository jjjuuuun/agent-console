import { useEffect, useRef } from "react";
import { Button } from "@agent-console/ui";

export interface LoadMoreFooterProps {
  hasMore: boolean;
  loading: boolean;
  onLoadMore(): void;
  /** 단추 문구 */
  label: string;
  /** 읽는 중 문구(스크린리더용) */
  loadingLabel: string;
  /** true면 단추가 화면에 들어올 때 자동으로 더 읽는다(IntersectionObserver가 있을 때만). 단추는 늘 남는다. 기본 true */
  auto?: boolean;
}

/**
 * 목록 끝의 [더 불러오기] 단추와 무한 스크롤 감시(표현 컴포넌트). 더 없으면 아무것도 그리지 않는다.
 * 키보드는 단추 하나로 충분하고, 자동 읽기는 보조다.
 */
export function LoadMoreFooter({ hasMore, loading, onLoadMore, label, loadingLabel, auto = true }: LoadMoreFooterProps) {
  const ref = useRef<HTMLDivElement>(null);
  const loadRef = useRef(onLoadMore);
  useEffect(() => {
    loadRef.current = onLoadMore;
  });
  useEffect(() => {
    const el = ref.current;
    if (!auto || !hasMore || loading || el === null || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting)) loadRef.current();
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, [auto, hasMore, loading]);
  if (!hasMore) return null;
  return (
    <div ref={ref} className="app-load-more">
      <Button size="sm" onClick={onLoadMore} disabled={loading} aria-busy={loading ? "true" : undefined}>
        {loading ? loadingLabel : label}
      </Button>
    </div>
  );
}
