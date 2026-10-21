import type { ChatReply, ChatTurn, Interaction, InteractionKindDescriptor, QueuedMessage } from "@agent-console/contracts";

export type { ChatReply, ChatTurn, Interaction, InteractionKindDescriptor, QueuedMessage };

/** `chat.reply_display` 값. 문자열로 받고 모르는 값은 `separate`로 취급한다. */
export type ReplyDisplay = "separate" | "merged" | "final_only";

/** 한 턴의 답변 한 개. 스트리밍 중이면 `streaming`. */
export type ReplyItem = ChatReply & { streaming?: boolean };

/** 아바타 지정(글자·CSS 색). 해석은 앱이 한다(`attributes.ui` → 이름 첫 글자 + id 해시 색). 없으면 이름·id로 그린다. */
export interface AvatarSpec {
  text?: string;
  color?: string;
}

/** 진행 칩 아바타: 색 해시 키(`id`)와 첫 글자 폴백(`name`)에 표시 설정을 겹친다. */
export interface StepAvatar extends AvatarSpec {
  id: string;
  name: string;
}

export interface AgentView {
  /** 아바타 글자·색. 앱이 에이전트 정의의 표시 설정에서 해석한다 */
  avatar?: AvatarSpec;
  name: string;
  role?: string;
  /** 서브에이전트 답변이면 위임자 이름. "{위임자} 안의 {대상}"으로 표기한다. */
  parentName?: string;
  /** 독립 위임으로 불려 답한 대상이면 위임자 이름. "{위임자}가 맡긴 {대상}"으로 표기한다(`parentName`보다 우선). */
  delegatedBy?: string;
  /** 이름 옆에 붙는 짧은 칩(예: 체험용 백엔드 표시). 문구와 여부는 앱이 데이터에서 정한다. */
  badge?: string;
}

/** 중첩 팀(자식 Run) 칩의 자식 실행 정보. 링크 주소·진행 숫자는 앱이 채운다. */
export interface ProgressChild {
  runId: string;
  /** [실행 상세 ↗] 링크 주소. */
  href: string;
  /** 자식 실행을 만든 부모 노드 이름. */
  nodeLabel: string;
  /** 진행 숫자. 앱이 두 값을 다 알 때만 준다(분모를 추측하지 않는다). */
  progress?: { done: number; total: number };
}

/**
 * 진행 줄 한 단계(위임 칩). 방식 라벨은 앱이 연결 종류 `title`에서 채운다.
 * 아래 선택 필드(`badge` 이하)는 전부 앱이 이벤트에서 만든 데이터이며 컴포넌트는 종류를 모른다.
 */
export interface ProgressStep {
  key: string;
  status: string;
  fromLabel: string;
  toLabel: string;
  methodLabel: string;
  methodDashed?: boolean;
  /** 칩 양 끝 노드의 작은 아바타(앱이 채팅 답변 머리와 같은 해석으로 채운다) */
  fromAvatar?: StepAvatar;
  toAvatar?: StepAvatar;
  durationMs?: number;
  /** 들여 쓰기 단계(0 이상 정수). 화면은 `min(indent, 4)` 단계까지 그린다. */
  indent: number;
  href?: string;
  /** 상태 문구를 이 문자열로 대신한다(예: 사유가 붙은 "건너뜀(이어 가기)"). */
  statusLabel?: string;
  /** 연결 없이 노드 하나만 보인다(방식·화살표 없음). */
  solo?: boolean;
  /** 칩 뒤 짧은 배지 문구(예: "별도 세션"). 앱이 `messages`/디스크립터에서 채운다. */
  badge?: string;
  /** "2회차" 같은 회차 표기(앱이 번호를 +1 해서 만든 문구). */
  iterationLabel?: string;
  /** "호출 2" 같은 호출 표기. */
  callLabel?: string;
  /** `warning`이면 경고 표시(글자 `▲` + 테두리). 색만으로 전달하지 않는다. */
  tone?: "neutral" | "warning" | "info";
  /** 이 칩이 자식 실행(중첩 팀)을 나타낼 때. [실행 상세 ↗] 링크가 붙는다. */
  child?: ProgressChild;
  /** 이 칩 아래에 접고 펴는 단계들(보통 `child`가 있는 칩). 기본 접힘. */
  children?: readonly ProgressStep[];
  /**
   * 칩을 눌렀을 때 열 곳. 없으면 `onOpenRun(turn.run_id, key)`(키 = 노드 id). 자식 실행 안 노드(`runId`)나 반복 연결 상세(`edgeId`)처럼
   * 키로 알 수 없는 곳은 앱이 채운다.
   */
  openTarget?: { runId?: string; nodeId?: string; edgeId?: string };
  /** 마우스를 올렸을 때 보이는 설명. 없으면 들여 쓴 단계에 한해 기존 "같은 세션" 문구(배지·자식이 없을 때)를 쓴다. */
  hint?: string;
}

export interface QueuedRow {
  key: string;
  text: string;
  position: number;
  /** 재시작으로 멈춘 항목(실행·취소를 고른다). */
  held?: boolean;
}
