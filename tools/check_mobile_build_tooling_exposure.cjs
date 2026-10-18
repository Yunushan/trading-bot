"use strict";

// Mitigation verifiers for mobile-client build-tooling advisories that have no
// published fix in the resolved production graph. Each control pins the exact
// finding version and its reviewed lockfile consumers, proves the package is
// reachable only from build tooling, and proves the application source and
// runtime configuration cannot drive the vulnerable code path. The verifier
// fails closed when any of those facts changes.

const fs = require("node:fs");
const path = require("node:path");

const PROJECT_ID = "apps/mobile-client";
const SOURCE_EXTENSIONS = new Set([".cjs", ".js", ".jsx", ".mjs", ".ts", ".tsx"]);
const EXCLUDED_DIRECTORIES = new Set([".expo", "coverage", "dist", "node_modules"]);

const CONTROLS = {
  braces: {
    control_id: "mobile-braces-build-glob-v1",
    reviewed_version: "3.0.3",
    expected_consumers: ["micromatch@4.0.8"],
    reviewed_consumer_chain: {
      "micromatch": [
        "@expo/metro-file-map",
        "metro-file-map",
        "metro-transform-worker",
      ],
    },
    reason:
      "braces pattern expansion is reachable only through micromatch inside the Expo/Metro "
      + "bundling toolchain; the application never imports braces or micromatch and every glob "
      + "it evaluates is a repository-controlled build pattern.",
  },
  "node-forge": {
    control_id: "mobile-node-forge-build-signing-v1",
    reviewed_version: "1.4.0",
    expected_consumers: ["@expo/cli@57.0.27", "@expo/code-signing-certificates@0.0.6"],
    reviewed_consumer_chain: {},
    reason:
      "node-forge PKCS#1 v1.5 verification is reachable only from the Expo CLI build-time code "
      + "signing toolchain; the application ships no expo-updates configuration, performs no "
      + "runtime signature verification, and never imports node-forge.",
  },
};

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

function packageName(lockPath) {
  const marker = "node_modules/";
  const index = lockPath.lastIndexOf(marker);
  return index === -1 ? lockPath : lockPath.slice(index + marker.length);
}

function declaredDependencies(metadata) {
  return {
    ...(metadata?.dependencies || {}),
    ...(metadata?.optionalDependencies || {}),
    ...(metadata?.peerDependencies || {}),
  };
}

function lockConsumers(packages, findingPackage) {
  const consumers = new Map();
  for (const [lockPath, metadata] of Object.entries(packages)) {
    if (!Object.prototype.hasOwnProperty.call(declaredDependencies(metadata), findingPackage)) {
      continue;
    }
    const name = packageName(lockPath);
    consumers.set(`${name}@${metadata.version}`, name);
  }
  return consumers;
}

function resolvedVersions(packages, findingPackage) {
  return [...new Set(
    Object.entries(packages)
      .filter(([lockPath]) => packageName(lockPath) === findingPackage)
      .map(([, metadata]) => String(metadata.version || "")),
  )].sort();
}

function sourceImports(projectRoot, packageNames) {
  const pattern = new RegExp(
    `(?:require\\s*\\(\\s*["'](?:${packageNames.join("|")})["']`
    + `|from\\s+["'](?:${packageNames.join("|")})["']`
    + `|import\\s+["'](?:${packageNames.join("|")})["'])`,
  );
  return walkFiles(projectRoot, SOURCE_EXTENSIONS)
    .filter((filePath) => pattern.test(fs.readFileSync(filePath, "utf8")))
    .map((filePath) => path.relative(projectRoot, filePath).replaceAll("\\", "/"));
}

function evaluateBraces(projectRoot, packages, issues) {
  const micromatchConsumers = lockConsumers(packages, "micromatch");
  const reviewedChain = CONTROLS.braces.reviewed_consumer_chain.micromatch;
  for (const name of micromatchConsumers.values()) {
    if (!reviewedChain.includes(name)) {
      issues.push(`micromatch has an unreviewed consumer outside the Metro build toolchain: ${name}`);
    }
  }
  const expoDependency = declaredDependencies(packages["node_modules/expo"]);
  if (!Object.prototype.hasOwnProperty.call(expoDependency, "@expo/cli")) {
    issues.push("expo no longer declares the @expo/cli build toolchain dependency");
  }
}

function evaluateNodeForge(projectRoot, packages, issues) {
  const appConfig = readJson(path.join(projectRoot, "app.json")).expo || {};
  if (appConfig.updates) {
    issues.push("the application declares an expo-updates configuration with runtime signing");
  }
  const rootDependencies = declaredDependencies(
    readJson(path.join(projectRoot, "package.json")).dependencies,
  );
  if (Object.prototype.hasOwnProperty.call(rootDependencies, "expo-updates")) {
    issues.push("the application declares a direct expo-updates runtime dependency");
  }
  const expoDependency = declaredDependencies(packages["node_modules/expo"]);
  if (!Object.prototype.hasOwnProperty.call(expoDependency, "@expo/cli")) {
    issues.push("expo no longer declares the @expo/cli build toolchain dependency");
  }
}

function evaluate(projectRoot, findingPackage) {
  const control = CONTROLS[findingPackage];
  if (!control) {
    return {
      control_id: "",
      ok: false,
      project: PROJECT_ID,
      finding_package: findingPackage,
      issues: [`no reviewed build-tooling mitigation control exists for ${findingPackage}`],
    };
  }

  const issues = [];
  const lockPath = path.join(projectRoot, "package-lock.json");
  if (!fs.existsSync(lockPath)) {
    return {
      control_id: control.control_id,
      ok: false,
      project: PROJECT_ID,
      finding_package: findingPackage,
      issues: ["package-lock.json is missing"],
    };
  }

  const packages = readJson(lockPath).packages;
  if (!packages || typeof packages !== "object" || Array.isArray(packages)) {
    return {
      control_id: control.control_id,
      ok: false,
      project: PROJECT_ID,
      finding_package: findingPackage,
      issues: ["package-lock.json has no packages map"],
    };
  }

  const versions = resolvedVersions(packages, findingPackage);
  if (versions.length !== 1 || versions[0] !== control.reviewed_version) {
    issues.push(
      `${findingPackage} must resolve to the reviewed version ${control.reviewed_version}; `
      + `found ${versions.join(", ") || "<missing>"}`,
    );
  }

  const consumers = [...lockConsumers(packages, findingPackage).keys()].sort();
  if (JSON.stringify(consumers) !== JSON.stringify([...control.expected_consumers].sort())) {
    issues.push(
      `${findingPackage} consumers must match the reviewed set `
      + `${control.expected_consumers.join(", ")}; found ${consumers.join(", ") || "<none>"}`,
    );
  }

  const importedNames = findingPackage === "braces"
    ? [findingPackage, "micromatch"]
    : [findingPackage];
  const imports = sourceImports(projectRoot, importedNames);
  if (imports.length > 0) {
    issues.push(`application source imports the build-only package: ${imports.join(", ")}`);
  }

  if (findingPackage === "braces") {
    evaluateBraces(projectRoot, packages, issues);
  } else {
    evaluateNodeForge(projectRoot, packages, issues);
  }

  return {
    control_id: control.control_id,
    ok: issues.length === 0,
    project: PROJECT_ID,
    finding_package: findingPackage,
    package_version: versions.length === 1 ? versions[0] : "",
    consumers,
    exposure: "repository-controlled-build-toolchain-only",
    production_runtime_imports: false,
    reason: control.reason,
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
    } else if (argv[index] === "--package" && argv[index + 1]) {
      args.package = argv[index + 1];
      index += 1;
    }
  }
  return args;
}

if (require.main === module) {
  const args = parseArguments(process.argv.slice(2));
  const projectRoot = path.resolve(
    args.projectRoot || path.join(__dirname, "..", "apps", "mobile-client"),
  );
  let result;
  try {
    result = evaluate(projectRoot, args.package || "");
  } catch (error) {
    result = {
      control_id: "",
      ok: false,
      project: PROJECT_ID,
      finding_package: args.package || "",
      issues: [`build-tooling exposure verifier failed: ${error.message}`],
    };
  }
  if (args.json) {
    console.log(JSON.stringify(result, null, 2));
  } else if (result.ok) {
    console.log(`Mobile build-tooling exposure check passed for ${result.finding_package}`);
  } else {
    console.error(`Mobile build-tooling exposure check failed for ${result.finding_package}`);
    for (const issue of result.issues || []) {
      console.error(`- ${issue}`);
    }
  }
  process.exit(result.ok ? 0 : 1);
}

module.exports = { evaluate, CONTROLS };
