import { Component, lazy, Suspense, type ReactNode } from "react";
import type { LineChartProps } from "./types";

const RechartsLine = lazy(() => import("./RechartsLine"));

/** 지연 로드 중에는 `fallback`, 로드·렌더 실패는 `onFail`로 알리고 `failed`를 그린다. */
export function LineChartLazy(props: LineChartProps & { fallback: ReactNode; failed: ReactNode; onFail?: (e: unknown) => void }) {
  const { fallback, failed, onFail, ...chart } = props;
  return (
    <ChartBoundary failed={failed} onFail={onFail}>
      <Suspense fallback={fallback}>
        <RechartsLine {...chart} />
      </Suspense>
    </ChartBoundary>
  );
}

interface BoundaryProps {
  failed: ReactNode;
  onFail?: ((e: unknown) => void) | undefined;
  children: ReactNode;
}

class ChartBoundary extends Component<BoundaryProps, { failed: boolean }> {
  override state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  override componentDidCatch(error: unknown) {
    this.props.onFail?.(error);
  }
  override render() {
    return this.state.failed ? this.props.failed : this.props.children;
  }
}
