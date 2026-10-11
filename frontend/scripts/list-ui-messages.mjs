import ts from 'typescript';
import { readdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

const messages = new Map();
const ignoredAttributes = new Set(['className', 'id', 'key', 'value', 'defaultValue', 'name', 'type', 'role', 'href', 'src', 'accept', 'rel', 'target', 'style', 'variant', 'tone', 'method', 'tabIndex']);
function add(text, file) {
  text = text.replace(/\s+/g, ' ').trim();
  if (!/[a-zA-Z]{2}/.test(text) || text.length > 600) return;
  const files = messages.get(text) || new Set();
  files.add(file);
  messages.set(text, files);
}
function visitFile(path) {
  const source = ts.createSourceFile(path, readFileSync(path, 'utf8'), ts.ScriptTarget.Latest, true, path.endsWith('tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS);
  function visit(node) {
    if (ts.isJsxText(node)) add(node.text, path);
    if (ts.isStringLiteral(node)) {
      const p = node.parent;
      if (ts.isImportDeclaration(p) || ts.isExportDeclaration(p)) return;
      if (ts.isJsxAttribute(p) && (ignoredAttributes.has(p.name.text) || p.name.text.startsWith('data-'))) return;
      if (ts.isPropertyAssignment(p) && p.name === node) return;
      if (/\s+[A-Za-z]{2}|^[A-Z][a-z]+(?:$|[ /&:….,!?()'-])/.test(node.text) && !node.text.startsWith('/')) add(node.text, path);
    }
    if (ts.isTemplateExpression(node)) {
      const parts = [node.head.text, ...node.templateSpans.map((span, i) => `{${i}}${span.literal.text}`)].join('');
      if (/[A-Za-z]{2}\s|\s[A-Za-z]{2}/.test(parts) && !/className|aria-describedby|aria-labelledby/.test(node.parent.getText().slice(0, 30))) add(parts, path);
    }
    ts.forEachChild(node, visit);
  }
  visit(source);
}
function walk(dir) {
  for (const item of readdirSync(dir, { withFileTypes: true })) {
    if (item.name === 'generated' || item.name === 'i18n') continue;
    const path = join(dir, item.name);
    if (item.isDirectory()) walk(path);
    else if (/\.(tsx|ts)$/.test(item.name)) visitFile(path);
  }
}
walk('src');
const result = [...messages].map(([text, files]) => ({ text, files: [...files] }));
writeFileSync('test-artifacts/ui-messages.json', JSON.stringify(result, null, 2));
console.log(`${result.length} candidate messages written to test-artifacts/ui-messages.json`);
for (const [index, item] of result.entries()) console.log(`${index}\t${item.text}`);
