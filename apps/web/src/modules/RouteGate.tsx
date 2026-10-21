import { useEffect, useRef, type ReactNode } from "react";
import { Banner, useToast } from "@agent-console/ui";
import { LoadingBlock } from "../app/ErrorBlock";
import { messages as m } from "../app/messages";
import { useDelayed } from "../app/useDelayed";
import { useHasUnsaved } from "../definition/unsaved";
import { useRequires } from "./ModulesContext";
import { FeatureOffScreen, type FeatureOffScreenProps } from "./FeatureOffScreen";

export interface RouteGateProps extends Omit<FeatureOffScreenProps, "unmet"> {
  requires: readonly string[];
  children: ReactNode;
}

/**
 * 라우트 문지기: `requires`를 만족하면 화면(children), 만족하지 못하면 꺼진 기능 안내 화면.
 * - 목록을 받기 전에는 안내 화면도 본문도 그리지 않는다(깜박임 방지, 200ms 넘으면 스피너).
 * - 보던 화면이 꺼졌어도 저장 안 된 변경이 있으면 내리지 않고 경고 배너만 얹는다.
 * - 안내 화면을 보던 중 기능이 켜지면 토스트 후 원래 화면으로 바뀐다(주소는 그대로).
 */
export function RouteGate({ requires, children, ...off }: RouteGateProps) {
  const r = useRequires(requires);
  const toast = useToast();
  // 저장 안 된 변경은 이 화면에서만 생길 수 있다(안내 화면에는 편집기가 없고, 다른 화면으로는 이탈 확인이 막는다).
  const unsaved = useHasUnsaved();
  const wasOff = useRef(false);
  const showSpinner = useDelayed(r.phase === "loading");
  const holding = r.phase === "unmet" && unsaved;

  useEffect(() => {
    if (r.phase === "met") {
      if (wasOff.current) toast({ tone: "success", text: m.moduleOff.enabledToast });
      wasOff.current = false;
    } else if (r.phase === "unmet" && !holding) {
      wasOff.current = true;
    }
  }, [r.phase, holding, toast]);

  if (r.phase === "loading") return showSpinner ? <LoadingBlock label={m.moduleOff.loading} /> : null;
  if (r.phase === "met") return <>{children}</>;
  if (holding) {
    return (
      <>
        <Banner tone="warning">{m.moduleOff.unsavedBanner}</Banner>
        {children}
      </>
    );
  }
  return <FeatureOffScreen {...off} unmet={r.unmet} />;
}
