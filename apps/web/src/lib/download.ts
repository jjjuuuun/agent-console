/**
 * Blob을 브라우저 다운로드로 내려 준다(`<a download>` + 임시 URL). 토큰 헤더가 필요한 응답은 fetch로 받아
 * 이 함수로 저장한다(`<a href>` 직접 링크 금지). DOM 전역은 인자로 주입할 수 있다(테스트).
 */
export function saveBlob(
  blob: Blob,
  filename: string,
  env: { document: Document; url: Pick<typeof URL, "createObjectURL" | "revokeObjectURL"> } = { document, url: URL },
): void {
  const href = env.url.createObjectURL(blob);
  const link = env.document.createElement("a");
  link.href = href;
  link.download = filename;
  link.rel = "noopener";
  link.style.display = "none";
  env.document.body.appendChild(link);
  link.click();
  link.remove();
  // 일부 브라우저는 클릭 직후 해제하면 다운로드가 끊긴다.
  setTimeout(() => env.url.revokeObjectURL(href), 10_000);
}
