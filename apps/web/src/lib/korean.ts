/** 한글 받침 유무로 목적격 조사를 고른다: 받침 있으면 "을", 없으면 "를". 한글이 아닌 끝 글자(숫자·영문 등)는 "을(를)"로 둔다. */
export function objectParticle(word: string): string {
  const last = word.trimEnd().slice(-1);
  if (last === "") return "을(를)";
  const code = last.charCodeAt(0);
  if (code < 0xac00 || code > 0xd7a3) return "을(를)";
  return (code - 0xac00) % 28 === 0 ? "를" : "을";
}
