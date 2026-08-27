"use strict";

const fs = require("node:fs");
const path = require("node:path");

const CONTROL_ID = "mobile-image-size-build-only-v1";
const PROJECT_ID = "apps/mobile-client";
const FINDING_PACKAGE = "image-size";
const PATCHED_PACKAGE_NAME = "image-size-next";
const PATCHED_PACKAGE_VERSION = "1.2.2";
const VULNERABLE_FORMATS = ["avif", "heic", "heif", "icns", "jxl"];
const METRO_IMAGE_FORMATS = ["bmp", "gif", "jpeg", "jpg", "ktx", "png", "psd", "svg", "tiff", "webp"];
const SOURCE_IMPORT_PATTERN = /(?:require\s*\(\s*["']image-size["']|from\s*["']image-size["']|import\s*["']image-size["'])/;

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, "utf8"));
}

function walkFiles(root, options = {}) {
  const excluded = new Set(options.excludedDirectories || []);
  const extensions = new Set(options.extensions || []);
  const files = [];
  const pending = [root];
  while (pending.length > 0) {
    const current = pending.pop();
    for (const entry of fs.readdirSync(current, { withFileTypes: true })) {
      if (entry.isDirectory()) {
        if (!excluded.has(entry.name)) {
          pending.push(path.join(current, entry.name));
        }
      } else if (entry.isFile() && (extensions.size === 0 || extensions.has(path.extname(entry.name)))) {
        files.push(path.join(current, entry.name));
      }
    }
  }
  return files.sort();
}

function lockPathToFilesystem(projectRoot, lockPath) {
  return path.join(projectRoot, ...lockPath.split("/"));
}

function lockPackageParent(lockPath, packageName) {
  const topLevelPath = `node_modules/${packageName}`;
  const nestedSuffix = `/node_modules/${packageName}`;
  if (lockPath === topLevelPath) {
    return "";
  }
  if (lockPath.endsWith(nestedSuffix)) {
    return lockPath.slice(0, -nestedSuffix.length);
  }
  return null;
}

function resolveDependencyPackage(packages, consumer, dependencyName) {
  const consumerPath = consumer.lock_path;
  return Object.entries(packages)
    .map(([lockPath, metadata]) => ({
      lock_path: lockPath,
      metadata,
      parent: lockPackageParent(lockPath, dependencyName),
    }))
    .filter(({ parent }) => (
      parent !== null
      && (!parent || consumerPath === parent || consumerPath.startsWith(`${parent}/`))
    ))
    .sort((left, right) => right.parent.length - left.parent.length)[0] || null;
}

function dependencyConsumers(packages) {
  return Object.entries(packages)
    .filter(([, metadata]) => {
      const dependencySets = [metadata?.dependencies, metadata?.optionalDependencies];
      return dependencySets.some((dependencies) => dependencies?.[FINDING_PACKAGE]);
    })
    .map(([lockPath, metadata]) => ({
      lock_path: lockPath,
      name: lockPath.split("/").at(-1),
      version: String(metadata.version || ""),
    }))
    .sort((left, right) => left.lock_path.localeCompare(right.lock_path));
}

function inspectMetroConsumer(projectRoot, consumer, packages, issues) {
  if (consumer.name !== "metro") {
    issues.push(`${FINDING_PACKAGE} has a non-Metro consumer: ${consumer.lock_path}`);
    return null;
  }

  const resolvedDependency = resolveDependencyPackage(packages, consumer, FINDING_PACKAGE);
  if (!resolvedDependency) {
    issues.push(`${FINDING_PACKAGE} has no lockfile resolution for ${consumer.lock_path}`);
    return null;
  }
  const resolvedPackageName = String(resolvedDependency.metadata?.name || FINDING_PACKAGE);
  const resolvedPackageVersion = String(resolvedDependency.metadata?.version || "");
  if (resolvedPackageName !== PATCHED_PACKAGE_NAME || resolvedPackageVersion !== PATCHED_PACKAGE_VERSION) {
    issues.push(
      `${FINDING_PACKAGE} must resolve to ${PATCHED_PACKAGE_NAME}@${PATCHED_PACKAGE_VERSION}; `
      + `found ${resolvedPackageName}@${resolvedPackageVersion || "<missing>"}`,
    );
  }

  const metroRoot = lockPathToFilesystem(projectRoot, consumer.lock_path);
  const sourceRoot = path.join(metroRoot, "src");
  const assetsPath = path.join(sourceRoot, "Assets.js");
  if (!fs.existsSync(assetsPath)) {
    issues.push(`Metro consumer is missing its auditable Assets.js boundary: ${consumer.lock_path}`);
    return null;
  }

  const importFiles = walkFiles(sourceRoot, { extensions: [".cjs", ".js", ".mjs"] })
    .filter((filePath) => SOURCE_IMPORT_PATTERN.test(fs.readFileSync(filePath, "utf8")));
  if (importFiles.length !== 1 || path.resolve(importFiles[0]) !== path.resolve(assetsPath)) {
    issues.push(`Metro's ${FINDING_PACKAGE} import surface changed: ${importFiles.join(", ") || "none"}`);
    return null;
  }

  let assets;
  try {
    assets = require(assetsPath);
  } catch (error) {
    issues.push(`Metro Assets.js could not be loaded: ${error.message}`);
    return null;
  }
  if (typeof assets.isAssetTypeAnImage !== "function" || typeof assets.getAssetSize !== "function") {
    issues.push("Metro's image-size guard functions are unavailable");
    return null;
  }

  const acceptedVulnerableFormats = VULNERABLE_FORMATS.filter((format) => assets.isAssetTypeAnImage(format));
  if (acceptedVulnerableFormats.length > 0) {
    issues.push(`Metro now accepts vulnerable parser formats: ${acceptedVulnerableFormats.join(", ")}`);
  }
  const rejectedExpectedFormats = METRO_IMAGE_FORMATS.filter((format) => !assets.isAssetTypeAnImage(format));
  if (rejectedExpectedFormats.length > 0) {
    issues.push(`Metro's reviewed image allowlist changed: ${rejectedExpectedFormats.join(", ")}`);
  }
  for (const format of VULNERABLE_FORMATS) {
    if (assets.getAssetSize(format, Buffer.from("untrusted"), `probe.${format}`) !== null) {
      issues.push(`Metro did not reject ${format} before invoking ${FINDING_PACKAGE}`);
    }
  }

  return {
    assets_path: path.relative(projectRoot, assetsPath).replaceAll("\\", "/"),
    import_files: importFiles.map((filePath) => path.relative(projectRoot, filePath).replaceAll("\\", "/")),
    accepted_image_formats: METRO_IMAGE_FORMATS,
    rejected_vulnerable_formats: VULNERABLE_FORMATS,
    resolved_package_name: resolvedPackageName,
    resolved_package_version: resolvedPackageVersion,
    resolved_package_path: resolvedDependency.lock_path,
  };
}

function inspectAppImports(projectRoot) {
  return walkFiles(projectRoot, {
    excludedDirectories: [".expo", "coverage", "dist", "node_modules"],
    extensions: [".cjs", ".js", ".jsx", ".mjs", ".ts", ".tsx"],
  })
    .filter((filePath) => SOURCE_IMPORT_PATTERN.test(fs.readFileSync(filePath, "utf8")))
    .map((filePath) => path.relative(projectRoot, filePath).replaceAll("\\", "/"));
}

function evaluate(projectRoot) {
  const issues = [];
  const lockPath = path.join(projectRoot, "package-lock.json");
  if (!fs.existsSync(lockPath)) {
    return { issues: ["package-lock.json is missing"] };
  }
  const lockfile = readJson(lockPath);
  const packages = lockfile?.packages;
  if (!packages || typeof packages !== "object" || Array.isArray(packages)) {
    return { issues: ["package-lock.json has no packages map"] };
  }

  const consumers = dependencyConsumers(packages);
  if (consumers.length === 0) {
    issues.push(`${FINDING_PACKAGE} has no declared lockfile consumer`);
  }
  const consumerEvidence = consumers
    .map((consumer) => inspectMetroConsumer(projectRoot, consumer, packages, issues))
    .filter(Boolean);

  const resolvedPackages = consumerEvidence.map((evidence) => ({
    name: evidence.resolved_package_name,
    version: evidence.resolved_package_version,
    path: evidence.resolved_package_path,
  }));
  const packageVersions = [...new Set(resolvedPackages.map((item) => item.version).filter(Boolean))];
  const packageVersion = packageVersions.length === 1 ? packageVersions[0] : "";
  if (resolvedPackages.length === 0 && consumers.length > 0) {
    issues.push(`${FINDING_PACKAGE} is missing from the installed production lock graph`);
  }

  const appSourceImports = inspectAppImports(projectRoot);
  if (appSourceImports.length > 0) {
    issues.push(`application source imports ${FINDING_PACKAGE}: ${appSourceImports.join(", ")}`);
  }

  return {
    control_id: CONTROL_ID,
    ok: issues.length === 0,
    project: PROJECT_ID,
    finding_package: FINDING_PACKAGE,
    package_version: packageVersion,
    resolved_packages: resolvedPackages,
    consumers: consumers.map((consumer) => `${consumer.name}@${consumer.version}`),
    consumer_evidence: consumerEvidence,
    app_source_imports: appSourceImports,
    exposure: "repository-controlled-build-assets-only",
    production_runtime_imports: false,
    issues,
  };
}

function parseArguments(argv) {
  const args = { json: false };
  for (let index = 0; index < argv.length; index += 1) {
    if (argv[index] === "--json") {
      args.json = true;
    } else if (argv[index] === "--project-root" && argv[index + 1]) {
      args.projectRoot = argv[index + 1];
      index += 1;
    }
  }
  return args;
}

if (require.main === module) {
  const args = parseArguments(process.argv.slice(2));
  const projectRoot = path.resolve(args.projectRoot || path.join(__dirname, "..", "apps", "mobile-client"));
  let result;
  try {
    result = evaluate(projectRoot);
  } catch (error) {
    result = {
      control_id: CONTROL_ID,
      ok: false,
      project: PROJECT_ID,
      finding_package: FINDING_PACKAGE,
      issues: [`mitigation verifier failed: ${error.message}`],
    };
  }
  if (args.json) {
    console.log(JSON.stringify(result, null, 2));
  } else if (result.ok) {
    console.log("Mobile image-size exposure check passed");
  } else {
    console.error("Mobile image-size exposure check failed");
    for (const issue of result.issues || []) {
      console.error(`- ${issue}`);
    }
  }
  process.exit(result.ok ? 0 : 1);
}

module.exports = { evaluate };
