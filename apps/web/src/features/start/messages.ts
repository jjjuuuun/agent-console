/** 첫 단계 안내의 문구(세 곳 — 채팅 시작하기 카드·채팅 빈 상태·팀 구성 목록 빈 상태 — 이 같은 표를 쓴다). */
export const startMessages = {
  title: "시작하기",
  close: "닫기",
  description: "처음이라면 아래 순서대로 진행하세요.",
  stepsLabel: "시작 순서",
  go: "바로가기",
  done: "완료",
  /** 단계 문구. 키는 `startSteps.ts`의 단계 id */
  steps: {
    create: { label: "팀 만들기", hint: "에이전트를 놓으면 입구·답변이 자동으로 연결됩니다", action: "새 팀 구성" },
    talk: { label: "대화 시작", hint: "처음이면 실행 백엔드를 고르라고 묻습니다", action: "새 대화" },
    review: { label: "결과 보기", hint: "실행 기록에서 각 단계의 결과를 확인합니다", action: "실행 기록" },
  } as Record<string, { label: string; hint: string; action: string }>,
} as const;
