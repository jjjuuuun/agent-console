import { Link } from "react-router";
import { StepGuide, type StepGuideStep } from "@agent-console/ui";
import { startMessages } from "./messages";
import { useStartGuide } from "./useStartGuide";

export interface StartGuideProps {
  /** 단계 버튼을 동작으로 바꾼다(단계 id -> 동작). 같은 화면 안에서 대화상자를 열 때만 쓴다. 기본은 모두 `to` 이동. */
  actionOverrides?: Readonly<Record<string, () => void>>;
  /** 단계 목록을 가로 3칸으로 */
  layout?: "row" | "column";
}

function renderLink({ to, className, children, dataAttrs }: { to: string; className: string; children: React.ReactNode; dataAttrs: Record<string, string> }) {
  return <Link to={to} className={className} {...dataAttrs}>{children}</Link>;
}

/**
 * 첫 단계 안내 한 덩어리: "직접 만들기" 단계. 세 곳(시작하기 카드·채팅 빈 상태·팀 목록 빈 상태)이 이것을 쓴다.
 */
export function StartGuide({ actionOverrides, layout = "column" }: StartGuideProps) {
  const g = useStartGuide();
  const steps: StepGuideStep[] = g.steps.map((s) => {
    const o = actionOverrides?.[s.id];
    if (o === undefined) return s;
    const { to: _to, ...rest } = s;
    void _to;
    return { ...rest, onAction: o };
  });
  return (
    <div className="start-guide" data-ready={g.ready ? "true" : "false"}>
      <StepGuide steps={steps} messages={{ stepsLabel: startMessages.stepsLabel, go: startMessages.go, done: startMessages.done }} renderLink={renderLink} layout={layout} />
    </div>
  );
}
