import { useLibMessages, type MessageTree } from "@agent-console/i18n";
import { defaultMessages as archDefaults, type ArchViewMessages } from "@agent-console/arch-view";
import { defaultUiMessages, type UiMessages } from "@agent-console/ui";
import { defaultTraceMessages, type TraceMessages } from "@agent-console/trace-view";

/** 현재 언어의 `@agent-console/trace-view` 문구(`TraceTimeline`의 `messages` prop). */
export function useTraceViewMessages(): TraceMessages {
  return useLibMessages("trace-view", defaultTraceMessages as unknown as MessageTree) as unknown as TraceMessages;
}

/** 현재 언어의 `@agent-console/arch-view` 문구(`ArchitectureDiagram`의 `messages` prop). */
export function useArchViewMessages(): ArchViewMessages {
  return useLibMessages("arch-view", archDefaults as unknown as MessageTree) as unknown as ArchViewMessages;
}

/** 현재 언어의 `@agent-console/ui` 문구(`ChipRow`·`Tabs` 등의 `messages` prop). */
export function useUiLibMessages(): UiMessages {
  return useLibMessages("ui", defaultUiMessages as unknown as MessageTree) as unknown as UiMessages;
}
