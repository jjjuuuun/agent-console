// `pnpm app`: 서버·웹이 준비될 때까지 기다리는 순수 도우미(fetch·sleep 주입). 실행은 scripts/app.mjs가 한다.

/** URL이 2xx로 응답할 때까지 기다린다. 응답 없음·503(not_ready)·그 밖의 오류는 계속 기다린다. 반환: 준비되면 true, `stop()`이 참이면 false. */
export async function waitForOk(url, { fetchFn = fetch, sleep = (ms) => new Promise((r) => setTimeout(r, ms)), intervalMs = 500, stop = () => false, onWait = () => {} } = {}) {
  let tries = 0;
  while (!stop()) {
    try {
      const res = await fetchFn(url);
      if (res.ok) return true;
    } catch {
      // 아직 연결되지 않음
    }
    onWait(tries++);
    await sleep(intervalMs);
  }
  return false;
}
