/** 자식 실행 표시용 짧은 id(앞 6자, 화면 명세 3.1). */
export function shortRunId(id: string): string {
  return id.slice(0, 6);
}
