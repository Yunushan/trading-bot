"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");
const { createRequire } = require("node:module");
const { test } = require("node:test");

const project = path.resolve(__dirname, "..");
const devtoolsRequire = createRequire(path.join(project, "node_modules/react-devtools-core/package.json"));
const postcssRequire = createRequire(path.join(project, "node_modules/postcss/package.json"));
const shell = devtoolsRequire("shell-quote");
const maps = postcssRequire("source-map-js");

// Exercise the published fixes through the real dependency callers. Quoted
// strings are never executed, and malformed maps are rejected before traversal.
test("shell-quote rejects line terminators in every string after a comment", () => {
  for (const terminator of ["\n", "\r", "\u2028", "\u2029"]) {
    const value = `first${terminator}second`;
    assert.throws(() => shell.quote(["echo", { comment: "fixture" }, value]), TypeError);
    assert.throws(() => shell.quote(["echo", { comment: "fixture" }, "safe", value]), TypeError);
    assert.throws(() => shell.quote(shell.parse("echo http://fixture/#fragment").concat(value)), TypeError);
  }
});

test("shell-quote preserves normal quoting and tokens before a comment", () => {
  const tokens = ["echo", "", "two words", "it's valid!", "a;literal", "C:\\fixture", "plain"];
  assert.deepEqual(shell.parse(shell.quote(tokens)), tokens);
  assert.equal(shell.quote(["echo", "first\nsecond", { comment: "fixture" }]), "echo 'first\nsecond' #fixture");
  assert.equal(shell.quote(["echo", { comment: "fixture" }, "safe"]), "echo #fixture safe");
});

const flatMap = { version: 3, sources: ["fixture.js"], names: [], mappings: "AAAA", sourcesContent: ["fixture();"] };
const indexedMap = (line, column = 0, map = flatMap) => ({ version: 3, sections: [{ offset: { line, column }, map }] });

test("source-map-js rejects invalid and excessive indexed offsets before traversal", () => {
  for (const value of [-1, 0.5, NaN, Infinity, 10000001, Number.MAX_SAFE_INTEGER]) {
    assert.throws(() => new maps.SourceMapConsumer(indexedMap(value)), /Section offset/);
  }
  for (const value of [-1, 0.5, NaN, Infinity]) {
    assert.throws(() => new maps.SourceMapConsumer(indexedMap(0, value)), /Section offset/);
  }
  assert.throws(() => new maps.SourceMapConsumer(indexedMap(6000000, 0, indexedMap(6000000))), /including offsets of nested sections/);
});

test("source-map-js retains valid indexed maps and flat serialization", () => {
  const consumer = new maps.SourceMapConsumer(indexedMap(2));
  assert.deepEqual(consumer.generatedPositionFor({ source: "fixture.js", line: 1, column: 0 }), { line: 3, column: 0 });
  const mappings = [];
  consumer.eachMapping(mapping => mappings.push(mapping));
  assert.deepEqual(mappings, [{ source: "fixture.js", generatedLine: 3, generatedColumn: 0, originalLine: 1, originalColumn: 0, name: null }]);
  assert.equal(consumer.sourceContentFor("fixture.js"), "fixture();");
  const generated = maps.SourceMapGenerator.fromSourceMap(new maps.SourceMapConsumer(flatMap)).toJSON();
  assert.equal(generated.mappings, "AAAA");
  assert.deepEqual(generated.sourcesContent, ["fixture();"]);
});

test("actual PostCSS consumer produces a usable map after the dependency update", () => {
  const postcss = require("postcss");
  const result = postcss([{ postcssPlugin: "synthetic-color", Declaration(node) { if (node.prop === "color") node.value = "blue"; } }]).process("a{color:red}", {
    from: "fixture.css", to: "out.css", map: { inline: false, annotation: false },
  });
  assert.equal(result.css, "a{color:blue}");
  const consumer = new maps.SourceMapConsumer(result.map.toJSON());
  const original = consumer.originalPositionFor({ line: 1, column: 2 });
  assert.equal(original.line, 1);
  assert.equal(original.source, "fixture.css");
});