"use strict";

const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");
const { createRequire } = require("node:module");
const zlib = require("node:zlib");

const UPSTREAM_URL = "https://registry.npmjs.org/node-forge/-/node-forge-1.4.0.tgz";
const UPSTREAM_SRI = "sha512-LarFH0+6VfriEhqMMcLX2F7SwSXeWwnEAJEsYm5QKWchiVYVvJyV9v7UDvUv+w5HO23ZpQTXDv/GxdDdMyOuoQ==";
const UPSTREAM_COMMIT = "ceba34402e329f0365134f23fe19898756527d65";
const QUALIFIED_BUILD_RUNTIME = { node: "v26.5.1", zlib: "1.3.2.1-motley-3246f1b" };
const VENDOR_PATH = "vendor/node-forge";
const UPSTREAM_FILE = "upstream-node-forge-1.4.0.tgz";
const PATCHED_FILE = "node-forge-1.4.0-backport.tgz";
const LOCAL_SPEC = `file:${VENDOR_PATH}/${PATCHED_FILE}`;
const TARGET = "package/lib/rsa.js";
const BEFORE = [
  "          // validate DigestInfo structure and element count",
  "          var capture = {};",
  "          var errors = [];",
  "          if(!asn1.validate(obj, digestInfoValidator, capture, errors) ||",
  "            obj.value.length !== 2) {",
].join("\n");
const AFTER = [
  "          // validate DigestInfo structure and element counts (outer DigestInfo",
  "          // and nested DigestAlgorithm). asn1.validate ignores extra children,",
  "          // so length must be checked explicitly at each nesting level to",
  "          // prevent low-exponent PKCS#1 v1.5 signature forgery (CVE-2026-85393).",
  "          var capture = {};",
  "          var errors = [];",
  "          if(!asn1.validate(obj, digestInfoValidator, capture, errors) ||",
  "            obj.value.length !== 2 ||",
  "            obj.value[0].value.length !==",
  "              (('parameters' in capture) ? 2 : 1) ||",
  "            (('parameters' in capture) && capture.parameters !== '')) {",
].join("\n");

function digest(bytes, algorithm = "sha256", encoding = "hex") {
  return crypto.createHash(algorithm).update(bytes).digest(encoding);
}

function integrity(bytes) {
  return `sha512-${digest(bytes, "sha512", "base64")}`;
}

function octal(header, start, length) {
  const text = header.subarray(start, start + length).toString("ascii").replace(/\0/g, "").trim();
  assert.match(text, /^[0-7]+$/, "invalid tar numeric field");
  return Number.parseInt(text, 8);
}

function readTar(bytes) {
  const tar = zlib.gunzipSync(bytes, { maxOutputLength: 8 * 1024 * 1024 });
  assert.equal(tar.length % 512, 0, "tar must end at a block boundary");
  const members = [];
  const names = new Set();
  let offset = 0;
  while (offset + 512 <= tar.length && tar.subarray(offset, offset + 512).some(value => value !== 0)) {
    const header = tar.subarray(offset, offset + 512);
    const name = header.subarray(0, 100).toString("utf8").split("\0")[0];
    assert.match(name, /^package\/[A-Za-z0-9_.\/-]+$/, "unexpected tar path");
    assert(!name.split("/").some(part => !part || part === "." || part === ".."), "unsafe tar path");
    assert(!names.has(name), "duplicate tar file");
    names.add(name);
    assert.equal(header[156], 48, "only regular files are allowed");
    assert(!header.subarray(345, 500).some(value => value !== 0), "tar path prefix is unsupported");
    const checksum = Array.from(header).reduce((sum, value, index) => sum + (index >= 148 && index < 156 ? 32 : value), 0);
    assert.equal(octal(header, 148, 8), checksum, "tar checksum mismatch");
    const size = octal(header, 124, 12);
    const end = offset + 512 + size;
    const next = offset + 512 + Math.ceil(size / 512) * 512;
    assert(next <= tar.length, "truncated tar file");
    assert(!tar.subarray(end, next).some(value => value !== 0), "nonzero tar padding");
    members.push({ name, header, data: tar.subarray(offset + 512, end) });
    offset = next;
  }
  assert(tar.length - offset >= 1024, "missing tar end markers");
  assert(!tar.subarray(offset).some(value => value !== 0), "unexpected data after tar end");
  return { tar, members, trailer: tar.subarray(offset) };
}

function patchSource(source) {
  const text = source.toString("utf8");
  assert.equal(text.split(BEFORE).length, 2, "upstream RSA patch anchor must occur exactly once");
  return Buffer.from(text.replace(BEFORE, AFTER), "utf8");
}

function patchedArchive(upstream) {
  assert.equal(integrity(upstream), UPSTREAM_SRI, "official upstream integrity mismatch");
  const parsed = readTar(upstream);
  assert.equal(parsed.members.length, 59, "official package file count changed");
  const parts = [];
  let targetCount = 0;
  for (const member of parsed.members) {
    let header = member.header;
    let data = member.data;
    if (member.name === TARGET) {
      targetCount += 1;
      data = patchSource(data);
      header = Buffer.from(header);
      header.write(`${data.length.toString(8).padStart(11, "0")}\0`, 124, 12, "ascii");
      header.fill(32, 148, 156);
      const checksum = Array.from(header).reduce((sum, value) => sum + value, 0);
      header.write(`${checksum.toString(8).padStart(6, "0")}\0 `, 148, 8, "ascii");
    }
    parts.push(header, data, Buffer.alloc((512 - data.length % 512) % 512));
  }
  assert.equal(targetCount, 1, "official RSA source missing");
  return { parsed, tar: Buffer.concat([...parts, parsed.trailer]) };
}

function patchText(source) {
  const start = source.toString("utf8").slice(0, source.indexOf(BEFORE)).split("\n").length;
  const oldLines = BEFORE.split("\n");
  const newLines = AFTER.split("\n");
  return `--- a/lib/rsa.js\n+++ b/lib/rsa.js\n@@ -${start},${oldLines.length} +${start},${newLines.length} @@\n`
    + oldLines.map(line => `-${line}\n`).join("") + newLines.map(line => `+${line}\n`).join("");
}

function encodeArchive(tar) {
  const gzip = zlib.gzipSync(tar, { level: 9 });
  gzip.writeUInt32LE(0, 4);
  gzip[9] = 255; // The payload does not depend on the build host's OS.
  return gzip;
}

function verifyPatchedGzip(bytes) {
  assert(bytes.length >= 18, "truncated patched gzip");
  assert.deepEqual(bytes.subarray(0, 10), Buffer.from([31, 139, 8, 0, 0, 0, 0, 0, 2, 255]), "patched gzip metadata must use DEFLATE, no optional fields, mtime 0, level 9 XFL and OS 255");
}

function currentBuildRuntime() {
  return { node: process.version, zlib: process.versions.zlib };
}

function standaloneLicense(bytes) {
  let end = bytes.length;
  while (end > 0 && bytes[end - 1] === 10) end -= 1;
  return Buffer.concat([bytes.subarray(0, end), Buffer.from("\n")]);
}

function provenance(upstream, patched, patch, buildRuntime = QUALIFIED_BUILD_RUNTIME) {
  const original = readTar(upstream).members;
  const modified = readTar(patched).members;
  return {
    version: 1,
    package: { name: "node-forge", version: "1.4.0", license: "(BSD-3-Clause OR GPL-2.0)" },
    upstream: { url: UPSTREAM_URL, integrity: UPSTREAM_SRI, sha256: digest(upstream) },
    upstream_backport: {
      commit: UPSTREAM_COMMIT,
      url: `https://github.com/digitalbazaar/forge/commit/${UPSTREAM_COMMIT}`,
      scope: "Only lib/rsa.js nested DigestAlgorithm element count and its comment; no unreleased changelog or version change.",
    },
    local_delta: "Additionally reject nonempty primitive NULL parameter contents (capture.parameters !== '').",
    archive_build: {
      command: "node tools/check_mobile_node_forge_backport.cjs --build --upstream <verified-tar> --project-root apps/mobile-client",
      profile: "preserved tar metadata/order, gzip level 9, mtime 0, OS 255",
      runtime: buildRuntime,
      reproducibility: "Exact compressed-byte regeneration is qualified only on the recorded Node/zlib builder. Other supported runtimes validate the pinned integrity, gzip metadata and exact canonical tar.",
    },
    patched: { file: PATCHED_FILE, integrity: integrity(patched), sha256: digest(patched), tar_sha256: digest(zlib.gunzipSync(patched)) },
    patch_sha256: digest(patch),
    changed_files: ["lib/rsa.js"],
    limitations: [
      "Node lib/index.js and actual Expo consumers are qualified. Bundled dist/*.min.js and maps remain byte-identical upstream artifacts and are not repaired or qualified by this backport.",
      "Package identity and version remain node-forge@1.4.0. GHSA-86w9-cpqp-85rv remains reported by npm audit; no exception, renamed package, version claim or source exclusion is used.",
    ],
    retirement: "Replace the local payload with a verified, recognized upstream fixed release and rerun behavioral, consumer and audit checks.",
    files: original.map((member, index) => ({
      path: member.name.slice(8), upstream_sha256: digest(member.data), patched_sha256: digest(modified[index].data),
    })),
  };
}

function build(upstreamPath, projectRoot) {
  const buildRuntime = currentBuildRuntime();
  assert.deepEqual(buildRuntime, QUALIFIED_BUILD_RUNTIME, "regeneration requires the qualified Node/zlib builder; verification remains portable");
  const upstream = fs.readFileSync(upstreamPath);
  const { parsed, tar } = patchedArchive(upstream);
  const patched = encodeArchive(tar);
  const patch = Buffer.from(patchText(parsed.members.find(member => member.name === TARGET).data));
  const vendor = path.join(projectRoot, VENDOR_PATH);
  fs.mkdirSync(vendor, { recursive: true });
  fs.writeFileSync(path.join(vendor, UPSTREAM_FILE), upstream);
  fs.writeFileSync(path.join(vendor, PATCHED_FILE), patched);
  fs.writeFileSync(path.join(vendor, "rsa-nested-digestalgorithm.patch"), patch);
  fs.writeFileSync(path.join(vendor, "LICENSE"), standaloneLicense(parsed.members.find(member => member.name === "package/LICENSE").data));
  fs.writeFileSync(path.join(vendor, "provenance.json"), `${JSON.stringify(provenance(upstream, patched, patch, buildRuntime), null, 2)}\n`);
  return verifyBundle(projectRoot);
}

function verifyBundle(projectRoot) {
  const vendor = path.join(projectRoot, VENDOR_PATH);
  const upstream = fs.readFileSync(path.join(vendor, UPSTREAM_FILE));
  const patched = fs.readFileSync(path.join(vendor, PATCHED_FILE));
  verifyPatchedGzip(patched);
  const { parsed, tar } = patchedArchive(upstream);
  const actual = readTar(patched);
  assert.deepEqual(actual.tar, tar, "patched archive is not the exact bounded backport");
  if (process.version === QUALIFIED_BUILD_RUNTIME.node && process.versions.zlib === QUALIFIED_BUILD_RUNTIME.zlib) {
    assert.deepEqual(patched, encodeArchive(tar), "patched gzip does not match the qualified builder");
  }
  const patch = fs.readFileSync(path.join(vendor, "rsa-nested-digestalgorithm.patch"));
  assert.equal(patch.toString("utf8"), patchText(parsed.members.find(member => member.name === TARGET).data), "patch description drift");
  assert.deepEqual(JSON.parse(fs.readFileSync(path.join(vendor, "provenance.json"), "utf8")), provenance(upstream, patched, patch), "provenance drift");
  assert.deepEqual(fs.readFileSync(path.join(vendor, "LICENSE")), standaloneLicense(parsed.members.find(member => member.name === "package/LICENSE").data), "standalone license drift");
  assert.deepEqual(JSON.parse(actual.members.find(member => member.name === "package/package.json").data).name, "node-forge");
  return { members: actual.members, integrity: integrity(patched) };
}

function installedFiles(root) {
  const files = [];
  function visit(current, prefix) {
    for (const entry of fs.readdirSync(current, { withFileTypes: true })) {
      assert(!entry.isSymbolicLink(), "installed payload links are forbidden");
      const name = prefix ? `${prefix}/${entry.name}` : entry.name;
      if (entry.isDirectory()) visit(path.join(current, entry.name), name);
      else {
        assert(entry.isFile(), "unexpected installed payload file type");
        files.push(name);
      }
    }
  }
  visit(root, "");
  return files.sort();
}

function verifyInstalled(root, members) {
  assert.deepEqual(installedFiles(root), members.map(member => member.name.slice(8)).sort(), "installed payload file set drift");
  for (const member of members) {
    assert.deepEqual(fs.readFileSync(path.join(root, member.name.slice(8))), member.data, `installed payload drift: ${member.name}`);
  }
}

function verifyProject(projectRoot) {
  const bundle = verifyBundle(projectRoot);
  const manifest = JSON.parse(fs.readFileSync(path.join(projectRoot, "package.json"), "utf8"));
  assert.equal(manifest.dependencies?.["node-forge"], LOCAL_SPEC, "required local dependency missing");
  assert.equal(manifest.overrides?.["node-forge"], "$node-forge", "required root dependency override missing");
  const lock = JSON.parse(fs.readFileSync(path.join(projectRoot, "package-lock.json"), "utf8"));
  const forgeEntries = Object.entries(lock.packages).filter(([key]) => /(?:^|\/)node_modules\/node-forge$/.test(key));
  assert(forgeEntries.length > 0, "locked node-forge package missing");
  for (const [key, entry] of forgeEntries) {
    assert(key.startsWith("node_modules/") && !key.split("/").some(part => !part || part === "." || part === ".."), "unsafe lock package path");
    assert.equal(entry.version, "1.4.0", "upstream package version must remain truthful");
    assert.equal(entry.resolved, LOCAL_SPEC, "locked package bypasses local backport");
    assert.equal(entry.integrity, bundle.integrity, "locked backport integrity mismatch");
    verifyInstalled(path.join(projectRoot, key), bundle.members);
  }
  const consumers = Object.entries(lock.packages).filter(([, entry]) => entry.dependencies?.["node-forge"]);
  assert(consumers.some(([key]) => key === "node_modules/@expo/cli"), "actual Expo CLI consumer missing");
  assert(consumers.some(([key]) => key === "node_modules/@expo/code-signing-certificates"), "actual Expo certificate consumer missing");
  const resolutions = consumers.map(([key]) => {
    const consumerRequire = createRequire(path.join(projectRoot, key, "package.json"));
    const resolved = consumerRequire.resolve("node-forge");
    const root = path.dirname(consumerRequire.resolve("node-forge/package.json"));
    assert.equal(resolved, path.join(root, "lib/index.js"), "consumer must use the repaired Node entry");
    assert(forgeEntries.some(([forgeKey]) => path.resolve(projectRoot, forgeKey) === root), "consumer resolved an unlocked payload");
    verifyInstalled(root, bundle.members);
    return { consumer: key, resolved: path.relative(projectRoot, resolved).replaceAll(path.sep, "/") };
  });
  return { ok: true, package: "node-forge@1.4.0", files: bundle.members.length, changed_files: ["lib/rsa.js"], integrity: bundle.integrity, consumers: resolutions, audit_status: "GHSA-86w9-cpqp-85rv remains reportable; this checker does not suppress npm audit." };
}

module.exports = { build, encodeArchive, integrity, patchSource, patchedArchive, readTar, standaloneLicense, verifyBundle, verifyInstalled, verifyProject };

if (require.main === module) {
  const args = process.argv.slice(2);
  const projectIndex = args.indexOf("--project-root");
  const projectRoot = path.resolve(projectIndex < 0 ? path.join(__dirname, "../apps/mobile-client") : args[projectIndex + 1]);
  if (args.includes("--build")) {
    const upstreamIndex = args.indexOf("--upstream");
    assert(upstreamIndex >= 0 && args[upstreamIndex + 1], "--build requires --upstream");
    const result = build(path.resolve(args[upstreamIndex + 1]), projectRoot);
    console.log(JSON.stringify({ ok: true, files: result.members.length, integrity: result.integrity }));
  } else console.log(JSON.stringify(verifyProject(projectRoot), null, 2));
}
