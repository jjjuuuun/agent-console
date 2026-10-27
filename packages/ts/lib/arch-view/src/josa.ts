/**
 * 한국어 조사 받침 맞춤 순수 함수. 라벨은 데이터 그대로 두고, 문구 틀의 `{이름|으로/로}`만 값에 맞춰 고른다.
 * 한글은 마지막 글자의 받침, 숫자는 읽는 소리, 영문은 읽는 소리 추정으로 판단한다(규칙은 `hasBatchim` 주석).
 */

const HANGUL_START = 0xac00;
const HANGUL_END = 0xd7a3;
/** 숫자를 한글로 읽을 때 받침이 있는 숫자(영 일 삼 육 칠 팔). */
const DIGIT_BATCHIM = new Set(["0", "1", "3", "6", "7", "8"]);
/** 알파벳 이름(에프 엘 엠 엔 에스 알 엑스 에이치)이 받침으로 끝나는 글자. 약어(전부 대문자)를 읽을 때 쓴다. */
const LETTER_NAME_BATCHIM = new Set(["F", "H", "L", "M", "N", "R", "S", "X"]);
/** 일반 영단어 끝소리가 받침처럼 읽히는 글자(훅·툴·팀·펀·컵). */
const WORD_FINAL_BATCHIM = new Set(["k", "l", "m", "n", "p"]);

/** 받침 판단에서 건너뛰는 끝 글자(공백·괄호·따옴표·구두점). */
const SKIP = /[\s)\]}>"'’”.,;:!?…·\-_/\\*]/;

/**
 * 말의 끝소리에 받침이 있는지.
 * - 한글: 마지막 글자의 종성.
 * - 숫자: 읽는 소리(0·1·3·6·7·8은 받침 있음).
 * - 영문: 두 글자 이상 전부 대문자면 약어로 보고 글자 이름(엘·엠·엔·알·에스 등)으로, 그 밖에는 끝 글자 k·l·m·n·p를 받침으로 본다.
 * 판단할 글자가 없으면 false. 추정이라 틀릴 수 있는 영문은 문구 쪽에서 `{x}`로 조사 없이 쓸 수 있다.
 */
export function hasBatchim(word: string): boolean {
  const chars = Array.from(word);
  let i = chars.length - 1;
  while (i >= 0 && SKIP.test(chars[i]!)) i--;
  if (i < 0) return false;
  const ch = chars[i]!;
  const code = ch.codePointAt(0)!;
  if (code >= HANGUL_START && code <= HANGUL_END) return (code - HANGUL_START) % 28 !== 0;
  if (/[0-9]/.test(ch)) return DIGIT_BATCHIM.has(ch);
  if (/[A-Za-z]/.test(ch)) {
    let j = i;
    while (j >= 0 && /[A-Za-z]/.test(chars[j]!)) j--;
    const run = chars.slice(j + 1, i + 1).join("");
    if (run.length >= 2 && run === run.toUpperCase()) return LETTER_NAME_BATCHIM.has(ch.toUpperCase());
    return WORD_FINAL_BATCHIM.has(ch.toLowerCase());
  }
  return false;
}

/** 끝 받침이 ㄹ인 한글 글자(으로/로 규칙). 영문·숫자는 ㄹ 받침으로 읽는 경우(l, 팔)만. */
function endsWithRieul(word: string): boolean {
  const chars = Array.from(word);
  let i = chars.length - 1;
  while (i >= 0 && SKIP.test(chars[i]!)) i--;
  if (i < 0) return false;
  const ch = chars[i]!;
  const code = ch.codePointAt(0)!;
  if (code >= HANGUL_START && code <= HANGUL_END) return (code - HANGUL_START) % 28 === 8;
  if (ch === "8") return true;
  if (/[A-Za-z]/.test(ch)) return hasBatchim(word) && ch.toLowerCase() === "l";
  return false;
}

/**
 * 조사 쌍(`받침 있을 때/없을 때`, 예 "은/는"·"이/가"·"을/를"·"과/와"·"으로/로")을 값에 맞춰 고른다.
 * "으로/로"는 ㄹ 받침 뒤에서 "로"를 쓴다.
 * @param word 조사가 붙을 말
 * @param pair `with/without` 형식. 슬래시가 없으면 그대로 돌려준다.
 */
export function josa(word: string, pair: string): string {
  const [withB, withoutB] = pair.split("/");
  if (withB === undefined || withoutB === undefined) return pair;
  if (!hasBatchim(word)) return withoutB;
  if (withB === "으로" && endsWithRieul(word)) return withoutB;
  return withB;
}

/** 값 뒤에 조사까지 붙인 글자. `withJosa("Hook", "으로/로")` → `"Hook으로"`. */
export function withJosa(word: string, pair: string): string {
  return `${word}${josa(word, pair)}`;
}
