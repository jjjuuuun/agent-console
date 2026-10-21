import { Linter } from "eslint";
import tseslint from "typescript-eslint";
import { expect, test } from "vitest";

import plugin from "../rules/button-name.js";

function lint(code: string) {
  const linter = new Linter();
  return linter.verify(
    code,
    [{ files: ["**/*.tsx"], languageOptions: { parser: tseslint.parser, parserOptions: { ecmaFeatures: { jsx: true } } }, plugins: { ac: plugin }, rules: { "ac/button-name": "error" } }],
    "a.tsx",
  );
}

test("아이콘만 있는 버튼은 막는다", () => {
  expect(lint("const a = <button><svg/></button>;")).toHaveLength(1);
  expect(lint("const a = <button><Icon name='x'/></button>;")).toHaveLength(1);
  expect(lint("const a = <button />;")).toHaveLength(1);
  expect(lint("const a = <button><span aria-hidden><svg/></span></button>;")).toHaveLength(1);
});

test("이름이 있으면 통과한다", () => {
  expect(lint("const a = <button aria-label='닫기'><svg/></button>;")).toHaveLength(0);
  expect(lint("const a = <button title='닫기'><svg/></button>;")).toHaveLength(0);
  expect(lint("const a = <button>저장</button>;")).toHaveLength(0);
  expect(lint("const a = <button><svg/>{label}</button>;")).toHaveLength(0);
  expect(lint("const a = <button><span>{label}</span></button>;")).toHaveLength(0);
  expect(lint("const a = <button {...props}><svg/></button>;")).toHaveLength(0);
  expect(lint("const a = <Button><svg/></Button>;")).toHaveLength(0);
  expect(lint("const a = <button type='submit' hidden />;")).toHaveLength(0);
});
