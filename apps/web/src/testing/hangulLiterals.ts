import ts from "typescript";

/** 한글(자모·호환 자모·음절) 한 글자. */
export const HANGUL = /[ᄀ-ᇿ㄰-㆏가-힣]/;

/**
 * 소스 텍스트의 문자열·템플릿·JSX 텍스트에서 한글이 든 조각을 돌려준다(주석은 보지 않는다).
 * 화면 문구를 코드에 두지 않았는지 검사하는 테스트(I.11, design §I18N.10 W1)가 쓴다.
 * @param fileName 확장자로 TS/TSX를 가린다.
 * @param text 소스 텍스트.
 * @returns 한글이 든 리터럴의 내용(줄 번호 포함: `줄: 내용`).
 */
export function findHangulLiterals(fileName: string, text: string): string[] {
  const source = ts.createSourceFile(fileName, text, ts.ScriptTarget.Latest, true, fileName.endsWith("x") ? ts.ScriptKind.TSX : ts.ScriptKind.TS);
  const hits: string[] = [];
  const visit = (node: ts.Node): void => {
    if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node) || ts.isJsxText(node) || ts.isTemplateHead(node) || ts.isTemplateMiddle(node) || ts.isTemplateTail(node)) {
      if (HANGUL.test(node.text)) hits.push(`${source.getLineAndCharacterOfPosition(node.getStart(source)).line + 1}: ${node.text.trim().slice(0, 60)}`);
    }
    ts.forEachChild(node, visit);
  };
  visit(source);
  return hits;
}
