import type { Formatter, FormatterRegistry } from "./types";

/** One particle rule: the form after a final consonant (batchim) and the form after a vowel. */
export interface ParticleRule {
  withBatchim: string;
  withoutBatchim: string;
  /** Written when the word does not end in a Hangul syllable. Default: `with(without)`. */
  unknown?: string;
  /** Treat a final ㄹ like no consonant (`으로`/`로`). */
  rieulAsVowel?: boolean;
}

/** Korean particle rules by name. Used as `{word, particle.<name>}` and `{word, particle.<name>.only}`. */
export const koreanParticles: Readonly<Record<string, ParticleRule>> = {
  object: { withBatchim: "을", withoutBatchim: "를", unknown: "을(를)" },
  subject: { withBatchim: "이", withoutBatchim: "가", unknown: "이(가)" },
  topic: { withBatchim: "은", withoutBatchim: "는", unknown: "은(는)" },
  and: { withBatchim: "과", withoutBatchim: "와", unknown: "과(와)" },
  direction: { withBatchim: "으로", withoutBatchim: "로", unknown: "(으)로", rieulAsVowel: true },
};

const HANGUL_FIRST = 0xac00;
const HANGUL_LAST = 0xd7a3;
const RIEUL = 8;

/** The particle for `word` by its last character; `word` itself is not included. */
export function particleFor(word: string, rule: ParticleRule): string {
  const last = word.trimEnd().slice(-1);
  const code = last === "" ? 0 : last.charCodeAt(0);
  if (code < HANGUL_FIRST || code > HANGUL_LAST) return rule.unknown ?? `${rule.withBatchim}(${rule.withoutBatchim})`;
  const batchim = (code - HANGUL_FIRST) % 28;
  if (batchim === 0 || (rule.rieulAsVowel === true && batchim === RIEUL)) return rule.withoutBatchim;
  return rule.withBatchim;
}

/**
 * Builds `particle.<name>` (value + particle) and `particle.<name>.only` (particle alone, for a value wrapped in
 * quotes: `‘{label}’{label, particle.object.only}`) formatters from a rule table.
 */
export function createParticleFormatters(rules: Readonly<Record<string, ParticleRule>> = koreanParticles): FormatterRegistry {
  const out: FormatterRegistry = {};
  for (const [name, rule] of Object.entries(rules)) {
    const only: Formatter = (value) => particleFor(String(value ?? ""), rule);
    out[`particle.${name.toLowerCase()}.only`] = only;
    out[`particle.${name.toLowerCase()}`] = (value) => `${String(value ?? "")}${particleFor(String(value ?? ""), rule)}`;
  }
  return out;
}
