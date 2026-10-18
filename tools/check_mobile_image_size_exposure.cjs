"use strict";

// Retirement guard for the mobile-client image-size exposure. The Expo/Metro
// production graph no longer depends on the unmaintained image-size package, so
// this control now asserts that the finding stays absent. Any reappearance in the
// production lock graph or in application source fails the guard and forces a
// fresh review instead of silently reinstating the vulnerable parser.

const fs = require("node:fs");
const path = require("node:path");

const CONTROL_ID = "mobile-image-size-retired-v1";
const PROJECT_ID = "apps/mobile-client";
const FINDING_PACKAGE = "image-size";
const PATCHED_PACKAGE_NAME = "image-size-next";
const PACKAGE_OVERRIDE = "npm:image-size-next@1.2.2";
const SOURCE_EXTENSIONS = new Set([".cjs", ".js", ".jsx", ".mjs", ".ts", ".tsx"]);
const EXCLUDED_DIRECTORIES = new Set([".expo", "coverage", "dist", "node_modules"]);
const SOURCE_IMPORT_PATTERN =
  /(?:require\s*\(\s*["']image-size["']|from\s*["']image-size["']|import\s*["']image-size["'])/;

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, "utf8"));
}

function walkFiles(root, extensions) {
  const files = [];
  const pending = [root];
  while (pending.length > 0) {
    const current = pending.pop();
    for (const entry of fs.readdirSync(current, { withFileTypes: true })) {
      if (entry.isDirectory()) {
        if (!EXCLUDED_DIRECTORIES.has(entry.name)) {
          pending.push(path.join(current, entry.name));
        }
      } else if (entry.isFile() && extensions.has(path.extname(entry.name))) {
        files.push(path.join(current, entry.name));
      }
    }
  }
  return files.sort();
}

function declaredDependencies(metadata) {
  return {
    ...(metadata?.dependencies || {}),
    ...(metadata?.optionalDependencies || {}),
    ...(metadata?.peerDependencies || {}),
  };
}

function lockOccurrences(packages) {
  const occurrences = [];
  for (const [lockPath, metadata] of Object.entries(packages)) {
    const segments = lockPath.split("/");
    const named = String(metadata?.name || "") === FINDING_PACKAGE;
    const pathed = segments.some((segment, index) => (
      segment === "node_modules" && segments[index + 1] === FINDING_PACKAGE
    ));
    const declared = Object.prototype.hasOwnProperty.call(
      declaredDependencies(metadata),
      FINDING_PACKAGE,
    );
    if (named || pathed || declared) {
      occurrences.push(lockPath || "<workspace root>");
    }
  }
  return occurrences.sort();
}

function evaluate(projectRoot) {
  const issues = [];
  const lockPath = path.join(projectRoot, "package-lock.json");
  if (!fs.existsSync(lockPath)) {
    return { control_id: CONTROL_ID, ok: false, project: PROJECT_ID, issues: ["package-lock.json is missing"] };
  }

  const packages = readJson(lockPath).packages;
  if (!packages || typeof packages !== "object" || Array.isArray(packages)) {
    return { control_id: CONTROL_ID, ok: false, project: PROJECT_ID, issues: ["package-lock.json has no packages map"] };
  }

  const occurrences = lockOccurrences(packages);
  if (occurrences.length > 0) {
    issues.push(`${FINDING_PACKAGE} is still present in the production lock graph: ${occurrences.join(", ")}`);
  }

  const sourceImports = walkFiles(projectRoot, SOURCE_EXTENSIONS)
    .filter((filePath) => SOURCE_IMPORT_PATTERN.test(fs.readFileSync(filePath, "utf8")))
    .map((filePath) => path.relative(projectRoot, filePath).replaceAll("\\", "/"));
  if (sourceImports.length > 0) {
    issues.push(`application source imports ${FINDING_PACKAGE}: ${sourceImports.join(", ")}`);
  }

  const override = readJson(path.join(projectRoot, "package.json"))?.overrides?.[FINDING_PACKAGE];
  if (override !== PACKAGE_OVERRIDE) {
    issues.push(
      `the reviewed fallback override for ${FINDING_PACKAGE} must stay ${PACKAGE_OVERRIDE}; `
      + `found ${override || "<missing>"}`,
    );
  }

  return {
    control_id: CONTROL_ID,
    ok: issues.length === 0,
    project: PROJECT_ID,
    finding_package: FINDING_PACKAGE,
    package_version: "",
    consumers: [],
    retired: occurrences.length === 0,
    fallback_override: override || "",
    reviewed_patched_fork: `${PATCHED_PACKAGE_NAME}@${PACKAGE_OVERRIDE.split("@").at(-1)}`,
    exposure: "absent-from-production-dependency-graph",
    production_runtime_imports: sourceImports.length > 0,
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
    console.log("Mobile image-size retirement check passed");
  } else {
    console.error("Mobile image-size retirement check failed");
    for (const issue of result.issues || []) {
      console.error(`- ${issue}`);
    }
  }
  process.exit(result.ok ? 0 : 1);
}

module.exports = { evaluate };
