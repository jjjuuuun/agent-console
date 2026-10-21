/** 목록의 단축키(F2·Delete)가 상세에 요청하는 동작. `token`이 바뀔 때마다 한 번 처리한다. */
export interface DetailRequest {
  id: string;
  action: "delete" | "rename";
  token: number;
}
