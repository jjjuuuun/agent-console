/** 로딩 자리 막대(스크린리더에는 busy 상태만 알린다). */
export function Skeleton({ rows = 4 }: { rows?: number }) {
  return (
    <div className="app-skeleton" aria-busy="true" role="status">
      {Array.from({ length: rows }, (_, i) => (
        <span key={i} className="app-skeleton-row" aria-hidden="true" />
      ))}
    </div>
  );
}
