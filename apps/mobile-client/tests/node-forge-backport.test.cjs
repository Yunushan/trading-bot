"use strict";

const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { createRequire } = require("node:module");
const { test } = require("node:test");
const zlib = require("node:zlib");
const { encodeArchive, integrity, patchedArchive, readTar, verifyBundle, verifyInstalled, verifyProject } = require("../../../tools/check_mobile_node_forge_backport.cjs");

const PROJECT = path.resolve(__dirname, "..");
const VENDOR = path.join(PROJECT, "vendor/node-forge");
const report = verifyProject(PROJECT);
const bundle = verifyBundle(PROJECT);
const forge = require("node-forge");
const certificates = require("@expo/code-signing-certificates");
// Only synthetic ephemeral keys; neither PEM nor private material is written.
const generated = crypto.generateKeyPairSync("rsa", {
  modulusLength: 2048,
  publicExponent: 3,
  privateKeyEncoding: { type: "pkcs1", format: "pem" },
  publicKeyEncoding: { type: "pkcs1", format: "pem" },
});
const keyPair = {
  privateKey: forge.pki.privateKeyFromPem(generated.privateKey),
  publicKey: forge.pki.publicKeyFromPem(generated.publicKey),
};
const digest = forge.md.sha256.create().update("synthetic mobile signature fixture").digest().getBytes();

function element(type, value, constructed = false) {
  return forge.asn1.create(forge.asn1.Class.UNIVERSAL, type, constructed, value);
}

function oid(value = forge.oids.sha256) {
  return element(forge.asn1.Type.OID, forge.asn1.oidToDer(value).getBytes());
}

function nil(value = "", constructed = false) {
  return element(forge.asn1.Type.NULL, value, constructed);
}

function encodedSignature(children, extraOuter = []) {
  const der = forge.asn1.toDer(element(forge.asn1.Type.SEQUENCE, [
    element(forge.asn1.Type.SEQUENCE, children, true),
    element(forge.asn1.Type.OCTETSTRING, digest),
    ...extraOuter,
  ], true)).getBytes();
  // Public signing API constructs normal PKCS#1 padding around deliberately
  // malformed DigestInfo. The verification API and parser are never replaced.
  return keyPair.privateKey.sign(der, "NONE");
}

function extract(members, destination) {
  for (const member of members) {
    const target = path.join(destination, member.name.slice(8));
    fs.mkdirSync(path.dirname(target), { recursive: true });
    fs.writeFileSync(target, member.data);
  }
}

function withTemporary(callback) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "mobile-forge-test-"));
  try { return callback(root); }
  finally {
    assert(path.dirname(root) === fs.realpathSync(os.tmpdir()) || path.dirname(root) === os.tmpdir());
    assert(path.basename(root).startsWith("mobile-forge-test-"));
    fs.rmSync(root, { recursive: true, force: true });
  }
}

test("complete payload retains upstream identity, license and 58 unaffected files", () => {
  const upstream = fs.readFileSync(path.join(VENDOR, "upstream-node-forge-1.4.0.tgz"));
  const patched = fs.readFileSync(path.join(VENDOR, "node-forge-1.4.0-backport.tgz"));
  const original = readTar(upstream).members;
  assert.equal(original.length, 59);
  assert.equal(bundle.members.length, 59);
  assert.equal(integrity(patched), report.integrity);
  const changes = original.filter((member, index) => !member.data.equals(bundle.members[index].data)).map(member => member.name);
  assert.deepEqual(changes, ["package/lib/rsa.js"]);
  const originalLicense = original.find(member => member.name === "package/LICENSE").data;
  const archiveLicense = bundle.members.find(member => member.name === "package/LICENSE").data;
  assert.deepEqual(archiveLicense, originalLicense, "archived license must remain byte-identical");
  assert.deepEqual(originalLicense.subarray(-2), Buffer.from("\n\n"));
  const notice = fs.readFileSync(path.join(VENDOR, "LICENSE"));
  assert.deepEqual(notice, originalLicense.subarray(0, originalLicense.length - 1), "only the standalone notice's extra final LF may change");
  assert.equal(notice[notice.length - 1], 10);
  assert.notEqual(notice[notice.length - 2], 10);
  const manifest = JSON.parse(bundle.members.find(member => member.name === "package/package.json").data);
  assert.equal(manifest.name, "node-forge");
  assert.equal(manifest.version, "1.4.0");
  assert.equal(manifest.license, "(BSD-3-Clause OR GPL-2.0)");
  const first = encodeArchive(patchedArchive(upstream).tar);
  assert.deepEqual(first, encodeArchive(patchedArchive(upstream).tar));
  assert.equal(first.readUInt32LE(4), 0);
  assert.equal(first[9], 255);
  const buildRuntime = JSON.parse(fs.readFileSync(path.join(VENDOR, "provenance.json"), "utf8")).archive_build.runtime;
  if (process.version === buildRuntime.node && process.versions.zlib === buildRuntime.zlib) {
    assert.deepEqual(first, patched);
  }
  assert.deepEqual(readTar(first).tar, readTar(patched).tar);
});

test("gzip metadata drift rejects even with matching compressed provenance hashes", () => {
  for (const [name, offset, value] of [["mtime", 4, 123], ["OS", 9, 0], ["flags", 3, 1], ["XFL", 8, 0]]) {
    withTemporary(root => {
      const vendor = path.join(root, "vendor/node-forge");
      fs.cpSync(VENDOR, vendor, { recursive: true });
      const file = path.join(vendor, "node-forge-1.4.0-backport.tgz");
      const bytes = fs.readFileSync(file);
      bytes[offset] = value;
      fs.writeFileSync(file, bytes);
      const metadataFile = path.join(vendor, "provenance.json");
      const metadata = JSON.parse(fs.readFileSync(metadataFile, "utf8"));
      metadata.patched.integrity = integrity(bytes);
      metadata.patched.sha256 = crypto.createHash("sha256").update(bytes).digest("hex");
      fs.writeFileSync(metadataFile, JSON.stringify(metadata));
      assert.throws(() => verifyBundle(root), /patched gzip metadata/, name);
    });
  }
});

test("upstream and bundled source/provenance drift fail closed", () => {
  for (const mutation of ["upstream", "unrelated payload", "provenance", "license"]) {
    withTemporary(root => {
      const vendor = path.join(root, "vendor/node-forge");
      fs.cpSync(VENDOR, vendor, { recursive: true });
      if (mutation === "upstream") {
        const file = path.join(vendor, "upstream-node-forge-1.4.0.tgz");
        const bytes = fs.readFileSync(file);
        bytes[100] ^= 1;
        fs.writeFileSync(file, bytes);
      } else if (mutation === "unrelated payload") {
        const file = path.join(vendor, "node-forge-1.4.0-backport.tgz");
        const tar = zlib.gunzipSync(fs.readFileSync(file));
        tar[512] ^= 1;
        fs.writeFileSync(file, zlib.gzipSync(tar));
      } else if (mutation === "provenance") {
        const file = path.join(vendor, "provenance.json");
        const metadata = JSON.parse(fs.readFileSync(file, "utf8"));
        metadata.package.version = "1.4.1";
        fs.writeFileSync(file, JSON.stringify(metadata));
      } else fs.appendFileSync(path.join(vendor, "LICENSE"), "changed");
      assert.throws(() => verifyBundle(root), undefined, mutation);
    });
  }
});

test("installed original RSA, extra file and changed license are rejected", () => {
  const original = readTar(fs.readFileSync(path.join(VENDOR, "upstream-node-forge-1.4.0.tgz"))).members;
  for (const mutation of ["original RSA", "extra file", "license"]) {
    withTemporary(root => {
      extract(bundle.members, root);
      verifyInstalled(root, bundle.members);
      if (mutation === "original RSA") fs.writeFileSync(path.join(root, "lib/rsa.js"), original.find(member => member.name === "package/lib/rsa.js").data);
      else if (mutation === "extra file") fs.writeFileSync(path.join(root, "additional.js"), "unexpected");
      else fs.appendFileSync(path.join(root, "LICENSE"), "changed");
      assert.throws(() => verifyInstalled(root, bundle.members), undefined, mutation);
    });
  }
});

test("real public RSA verification accepts both canonical optional parameter forms", () => {
  for (const children of [[oid()], [oid(), nil()]]) {
    assert.equal(keyPair.publicKey.verify(digest, encodedSignature(children)), true);
  }
  const message = forge.md.sha256.create().update("canonical public signing API");
  assert.equal(keyPair.publicKey.verify(message.digest().getBytes(), keyPair.privateKey.sign(message)), true);
});

test("real public RSA verification rejects malformed nested elements", () => {
  const garbage = () => element(forge.asn1.Type.OCTETSTRING, "garbage");
  const cases = [
    ["OID,NULL,garbage", [oid(), nil(), garbage()]],
    ["OID,garbage", [oid(), garbage()]],
    ["extra NULL", [oid(), nil(), nil()]],
    ["wrong tag", [oid(), element(forge.asn1.Type.INTEGER, "\x01")]],
    ["constructed NULL", [oid(), nil([], true)]],
    ["nonempty NULL", [oid(), nil("x")]],
    ["nonempty zero NULL", [oid(), nil("\x00")]],
    ["nonempty NULL plus garbage", [oid(), nil("x"), garbage()]],
  ];
  for (const [name, children] of cases) {
    assert.throws(() => keyPair.publicKey.verify(digest, encodedSignature(children)), /DigestInfo/, name);
  }
});

test("previous outer-count, OID, digest and MD5 NULL checks remain enforced", () => {
  assert.throws(() => keyPair.publicKey.verify(digest, encodedSignature([oid(), nil()], [nil()])), /DigestInfo/);
  assert.throws(() => keyPair.publicKey.verify(digest, encodedSignature([oid("1.2.3.4"), nil()])), /Unknown.*DigestAlgorithm/);
  assert.throws(() => keyPair.publicKey.verify(digest, encodedSignature([oid(forge.oids.md5)])), /Missing algorithm identifier NULL/);
  assert.equal(keyPair.publicKey.verify("wrong digest", encodedSignature([oid(), nil()])), false);
});

test("official unmodified public verifier reproduces both corrected acceptance defects", () => {
  withTemporary(root => {
    extract(readTar(fs.readFileSync(path.join(VENDOR, "upstream-node-forge-1.4.0.tgz"))).members, root);
    const original = require(path.join(root, "lib/index.js"));
    const publicKey = original.pki.publicKeyFromPem(generated.publicKey);
    assert.equal(publicKey.verify(digest, encodedSignature([oid(), nil(), element(forge.asn1.Type.OCTETSTRING, "garbage")])), true);
    assert.equal(publicKey.verify(digest, encodedSignature([oid(), nil("x")])), true);
  });
});

test("actual Expo consumers resolve repaired lib and certificate signing remains compatible", () => {
  assert(report.consumers.length >= 2);
  for (const consumer of report.consumers) {
    const consumerRequire = createRequire(path.join(PROJECT, consumer.consumer, "package.json"));
    const actual = consumerRequire("node-forge");
    assert.equal(actual, forge);
    const publicKey = actual.pki.publicKeyFromPem(generated.publicKey);
    assert.throws(() => publicKey.verify(digest, encodedSignature([oid(), nil("x")])), /DigestInfo/);
  }
  const now = Date.now();
  const certificate = certificates.generateSelfSignedCodeSigningCertificate({
    keyPair,
    validityNotBefore: new Date(now - 60 * 60 * 1000),
    validityNotAfter: new Date(now + 60 * 60 * 1000),
    commonName: "synthetic local mobile fixture",
  });
  const parsed = certificates.convertCertificatePEMToCertificate(certificates.convertCertificateToCertificatePEM(certificate));
  certificates.validateSelfSignedCertificate(parsed, keyPair);
  const message = Buffer.from("synthetic Expo manifest");
  const signature = certificates.signBufferRSASHA256AndVerify(keyPair.privateKey, parsed, message);
  assert.equal(parsed.publicKey.verify(forge.md.sha256.create().update(message.toString("binary")).digest().getBytes(), Buffer.from(signature, "base64").toString("binary")), true);
  const csr = certificates.generateCSR(keyPair, "synthetic local mobile fixture");
  assert.equal(certificates.convertCSRPEMToCSR(certificates.convertCSRToCSRPEM(csr)).verify(), true);
});
