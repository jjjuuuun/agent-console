/**
 * `<button>`에 접근성 이름이 없는 경우를 막는다(아이콘만 있는 버튼 금지, ux-overhaul §3.1-3).
 * 이름으로 인정: `aria-label`·`aria-labelledby`·`title` 속성, `hidden`(화면·접근성 트리에 없는 Enter 제출용 버튼), 펼침 속성(`{...props}`: 호출자가 이름을 준다고 본다),
 * 글자(JSXText)나 `{표현식}` 자식, 자식 컴포넌트 `<Foo />`는 이름으로 인정하지 않는다(아이콘일 수 있다).
 * 아이콘 버튼은 `IconButton`/`ActionButton`(`label` 필수)을 쓴다.
 * @type {import("eslint").Rule.RuleModule}
 */
export const buttonName = {
  meta: {
    type: "problem",
    docs: { description: "이름 없는 <button>(아이콘만) 금지: IconButton·ActionButton을 쓰거나 aria-label을 단다" },
    schema: [],
    messages: { unnamed: "접근성 이름이 없는 <button>입니다. IconButton/ActionButton(label 필수)을 쓰거나 aria-label을 다세요." },
  },
  create(context) {
    return {
      JSXElement(node) {
        const opening = node.openingElement;
        if (opening.name.type !== "JSXIdentifier" || opening.name.name !== "button") return;
        for (const attr of opening.attributes) {
          if (attr.type === "JSXSpreadAttribute") return;
          if (attr.type === "JSXAttribute" && attr.name.type === "JSXIdentifier" && ["aria-label", "aria-labelledby", "title", "hidden"].includes(attr.name.name)) return;
        }
        const named = node.children.some((child) => {
          if (child.type === "JSXText") return child.value.trim() !== "";
          if (child.type === "JSXExpressionContainer") return child.expression.type !== "JSXEmptyExpression";
          if (child.type === "JSXElement") return child.openingElement.name.type === "JSXIdentifier" && /^[a-z]/.test(child.openingElement.name.name) && hasText(child);
          return false;
        });
        if (!named) context.report({ node: opening, messageId: "unnamed" });
      },
    };
  },
};

/** 소문자 DOM 요소(span 등) 안에 글자·표현식이 있는지. 아이콘 `<svg>`만 있으면 false. */
function hasText(element) {
  return element.children.some((child) => {
    if (child.type === "JSXText") return child.value.trim() !== "";
    if (child.type === "JSXExpressionContainer") return child.expression.type !== "JSXEmptyExpression";
    if (child.type === "JSXElement") return hasText(child);
    return false;
  });
}

export default { rules: { "button-name": buttonName } };
