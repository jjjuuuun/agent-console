import { Component, type ErrorInfo, type ReactNode } from "react";
import { Button } from "@agent-console/ui";
import { messages } from "../app/messages";

export interface ScreenBoundaryProps {
  children: ReactNode;
  /** [다시 시도]: 경계를 풀기 전에 호출한다(예: 실패한 지연 로딩을 새로 만든다) */
  onRetry?: () => void;
  /** 불러오기 실패(`true`)인지 화면 렌더 중 예외(`false`)인지에 따라 문구를 고르기 위한 판별 */
  isLoadError?: (error: unknown) => boolean;
}

interface State {
  error: unknown;
  failed: boolean;
}

/**
 * 화면 영역의 오류 경계. 지연 로딩 실패(오프라인, 배포 직후 옛 청크)나 렌더 예외가 나도 셸(사이드바 등)은 유지하고
 * 이 영역에만 안내와 [다시 시도]·[새로 고침]을 보여 준다.
 */
export class ScreenBoundary extends Component<ScreenBoundaryProps, State> {
  override state: State = { error: undefined, failed: false };

  static getDerivedStateFromError(error: unknown): State {
    return { error, failed: true };
  }

  override componentDidCatch(error: unknown, info: ErrorInfo): void {
    console.error("[screen]", error, info.componentStack);
  }

  private retry = () => {
    this.props.onRetry?.();
    this.setState({ error: undefined, failed: false });
  };

  override render() {
    if (!this.state.failed) return this.props.children;
    const load = this.props.isLoadError?.(this.state.error) === true;
    return (
      <div className="app-error-block" role="alert">
        <h2 className="app-block-title">{load ? messages.common.screenLoadFailed : messages.common.screenCrashed}</h2>
        {load ? <p className="ac-text app-wrap">{messages.common.screenLoadFailedBody}</p> : null}
        <div className="app-inline-actions">
          <Button variant="primary" onClick={this.retry}>
            {messages.common.retry}
          </Button>
          <Button onClick={() => window.location.reload()}>{messages.common.reload}</Button>
        </div>
      </div>
    );
  }
}
