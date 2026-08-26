"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");

const SEVERITY_RANK = {
  info: 0,
  low: 1,
  moderate: 2,
  high: 3,
  critical: 4,
};

const MAX_EXCEPTION_REVIEW_DAYS = 45;

function normalizeSeverity(value) {
  return String(value ?? "").trim().toLowerCase();
}

function severityRank(value) {
  const normalized = normalizeSeverity(value);
  return Object.prototype.hasOwnProperty.call(SEVERITY_RANK, normalized)
    ? SEVERITY_RANK[normalized]
    : null;
}

function advisoryIds(vulnerability) {
  if (!Array.isArray(vulnerability?.via)) {
    return [];
  }

  return vulnerability.via
    .filter((item) => item && typeof item === "object")
    .map((item) => {
      const match = typeof item.url === "string" ? item.url.match(/(GHSA-[A-Z0-9-]+)/i) : null;
      return match ? match[1].toUpperCase() : String(item.source || "");
    })
    .filter(Boolean)
    .sort();
}

function sameValues(left, right) {
  return JSON.stringify([...left].sort()) === JSON.stringify([...right].sort());
}

function isoDateToUtc(value) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(String(value || ""))) {
    return null;
  }
  const timestamp = Date.parse(`${value}T00:00:00Z`);
  return Number.isFinite(timestamp) ? timestamp : null;
}

function elapsedDays(start, end) {
  return Math.floor((end - start) / (24 * 60 * 60 * 1000));
}

function mitigationReportsByControl(reports, errors) {
  const controls = new Map();
  for (const report of reports) {
    const controlId = typeof report?.control_id === "string" ? report.control_id.trim() : "";
    if (!controlId) {
      errors.push("every mitigation report must declare control_id");
      continue;
    }
    if (controls.has(controlId)) {
      errors.push(`duplicate mitigation report for ${controlId}`);
      continue;
    }
    controls.set(controlId, report);
  }
  return controls;
}

function evaluateAuditReport(report, policy, options = {}) {
  const project = options.project || "";
  const asOf = options.asOf || new Date().toISOString().slice(0, 10);
  const errors = [];
  const allowed = [];
  const allowedPackages = new Set();
  const projectPolicy = policy?.projects?.[project];
  const exceptions = Array.isArray(projectPolicy?.exceptions) ? projectPolicy.exceptions : [];
  const mitigationControls = mitigationReportsByControl(options.mitigationReports || [], errors);
  const vulnerabilityMap = report?.vulnerabilities;
  const hasVulnerabilityMap = vulnerabilityMap
    && typeof vulnerabilityMap === "object"
    && !Array.isArray(vulnerabilityMap);
  const vulnerabilities = hasVulnerabilityMap ? Object.entries(vulnerabilityMap) : [];
  const normalizedSeverities = new Map();

  for (const [packageName, vulnerability] of vulnerabilities) {
    if (!vulnerability || typeof vulnerability !== "object" || Array.isArray(vulnerability)) {
      errors.push(`Node audit finding for ${packageName} is malformed`);
      continue;
    }
    const normalized = normalizeSeverity(vulnerability.severity);
    normalizedSeverities.set(packageName, normalized);
    if (severityRank(normalized) === null) {
      errors.push(`Node audit finding for ${packageName} has unknown severity: ${normalized || "<missing>"}`);
    }
  }

  if (report?.error) {
    errors.push(`npm audit did not produce a vulnerability report: ${report.error.summary || report.error.message || "unknown error"}`);
  }
  if (!hasVulnerabilityMap) {
    errors.push("npm audit report is missing a vulnerabilities object");
  }

  if (!projectPolicy) {
    if (vulnerabilities.some(([name]) => severityRank(normalizedSeverities.get(name)) >= SEVERITY_RANK.high)) {
      errors.push(`no Node audit policy is defined for ${project}`);
    }
  }

  for (const exception of exceptions) {
    const packageName = exception?.package;
    const matchingEntry = vulnerabilities.find(([name]) => name === packageName);
    const vulnerability = matchingEntry?.[1];

    if (!packageName || !exception.reviewed || !exception.expires || !exception.reason) {
      errors.push("every Node audit exception must declare package, reviewed, expires, and reason");
      continue;
    }
    const reviewedAt = isoDateToUtc(exception.reviewed);
    const expiresAt = isoDateToUtc(exception.expires);
    if (reviewedAt === null || expiresAt === null || expiresAt < reviewedAt) {
      errors.push(`Node audit exception for ${packageName} has an invalid review window`);
      continue;
    }
    if (exception.expires < asOf) {
      errors.push(`Node audit exception for ${packageName} expired on ${exception.expires}`);
      continue;
    }
    if (!vulnerability) {
      errors.push(`Node audit exception for ${packageName} is stale; the package is no longer reported`);
      continue;
    }
    const vulnerabilitySeverity = normalizedSeverities.get(packageName);
    const vulnerabilityRank = severityRank(vulnerabilitySeverity);
    const maximumSeverity = normalizeSeverity(exception.max_severity || "high");
    const maximumRank = severityRank(maximumSeverity);
    if (vulnerabilityRank === null || maximumRank === null || vulnerabilityRank > maximumRank) {
      errors.push(`Node audit exception for ${packageName} does not permit ${vulnerability.severity} severity`);
      continue;
    }

    const expectedAdvisories = (exception.advisories || []).map((id) => String(id).toUpperCase()).sort();
    const actualAdvisories = advisoryIds(vulnerability);
    if (!sameValues(expectedAdvisories, actualAdvisories)) {
      errors.push(`Node audit exception for ${packageName} does not exactly match the reported advisories`);
      continue;
    }
    const requiredEffects = Array.isArray(exception.required_effects) ? exception.required_effects : [];
    const actualEffects = Array.isArray(vulnerability.effects) ? vulnerability.effects : [];
    if (!requiredEffects.every((effect) => actualEffects.includes(effect))) {
      errors.push(`Node audit exception for ${packageName} is outside its declared dependency effects`);
      continue;
    }
    const fixAvailability = String(exception.fix_availability || "").trim();
    if (fixAvailability === "breaking-graph-only") {
      if (vulnerability.fixAvailable?.isSemVerMajor !== true) {
        errors.push(`Node audit exception for ${packageName} requires a breaking graph remediation path`);
        continue;
      }
      if (
        vulnerability.fixAvailable.name !== exception.verified_fix_target
        || vulnerability.fixAvailable.version !== exception.verified_fix_version
      ) {
        errors.push(`Node audit exception for ${packageName} has an unreviewed npm remediation target`);
        continue;
      }
    } else if (fixAvailability === "none-published") {
      if (vulnerability.fixAvailable !== false) {
        errors.push(`Node audit exception for ${packageName} is valid only while npm reports no fix`);
        continue;
      }
    } else if (fixAvailability === "none-published-or-reviewed-breaking-graph") {
      const fix = vulnerability.fixAvailable;
      const reviewedBreakingGraph = fix?.isSemVerMajor === true
        && fix.name === exception.verified_fix_target
        && fix.version === exception.verified_fix_version;
      if (fix !== false && !reviewedBreakingGraph) {
        errors.push(
          `Node audit exception for ${packageName} permits only no published fix or the reviewed breaking graph remediation`,
        );
        continue;
      }
    } else {
      errors.push(`Node audit exception for ${packageName} has unknown fix_availability`);
      continue;
    }
    if (elapsedDays(reviewedAt, expiresAt) > MAX_EXCEPTION_REVIEW_DAYS) {
      errors.push(
        `Node audit exception for ${packageName} exceeds the ${MAX_EXCEPTION_REVIEW_DAYS}-day review window`,
      );
      continue;
    }
    const controlId = String(exception.mitigation_control || "").trim();
    const mitigation = mitigationControls.get(controlId);
    if (!controlId || !mitigation || mitigation.ok !== true) {
      errors.push(`Node audit exception for ${packageName} lacks passing mitigation evidence`);
      continue;
    }
    if (mitigation.project !== project || mitigation.finding_package !== packageName) {
      errors.push(`Node audit mitigation evidence for ${packageName} has the wrong scope`);
      continue;
    }
    if (mitigation.package_version !== exception.verified_package_version) {
      errors.push(`Node audit mitigation evidence for ${packageName} has an unreviewed package version`);
      continue;
    }
    if (!sameValues(mitigation.consumers || [], exception.verified_consumers || [])) {
      errors.push(`Node audit mitigation evidence for ${packageName} has unreviewed consumers`);
      continue;
    }

    allowedPackages.add(packageName);
    allowed.push({
      package: packageName,
      severity: vulnerability.severity,
      advisories: actualAdvisories,
      expires: exception.expires,
      reason: exception.reason,
    });
  }

  let changed = true;
  while (changed) {
    changed = false;
    for (const [name, vulnerability] of vulnerabilities) {
      if (allowedPackages.has(name) || normalizedSeverities.get(name) !== "high") {
        continue;
      }
      const stringDependencies = Array.isArray(vulnerability.via)
        ? vulnerability.via.filter((item) => typeof item === "string")
        : [];
      if (stringDependencies.some((dependency) => allowedPackages.has(dependency))) {
        allowedPackages.add(name);
        allowed.push({ package: name, severity: vulnerability.severity, inherited_from: stringDependencies });
        changed = true;
      }
    }
  }

  const unresolved = vulnerabilities
    .filter(([name]) => severityRank(normalizedSeverities.get(name)) >= SEVERITY_RANK.high)
    .filter(([name]) => !allowedPackages.has(name))
    .map(([name, vulnerability]) => ({
      package: name,
      severity: normalizedSeverities.get(name),
      advisories: advisoryIds(vulnerability),
      via: vulnerability.via || [],
      effects: vulnerability.effects || [],
    }));

  if (unresolved.length > 0) {
    errors.push(`${unresolved.length} high/critical Node audit finding(s) are not covered by policy`);
  }

  return {
    ok: errors.length === 0,
    project,
    as_of: asOf,
    high_or_critical_findings: vulnerabilities.filter(([name]) => severityRank(normalizedSeverities.get(name)) >= SEVERITY_RANK.high).length,
    allowed,
    unresolved,
    errors,
  };
}

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, "utf8"));
}

function runSelfTest() {
  const policy = {
    projects: {
      "apps/mobile-client": {
        exceptions: [{
          package: "image-size",
          advisories: ["GHSA-w3rx-r6r6-pgpr", "GHSA-5p2g-fcmc-qvqq"],
          expires: "2026-09-30",
          max_severity: "high",
          required_effects: ["metro"],
          reviewed: "2026-08-26",
          fix_availability: "none-published-or-reviewed-breaking-graph",
          verified_fix_target: "react-native",
          verified_fix_version: "0.86.3",
          mitigation_control: "mobile-image-size-build-only-v1",
          verified_package_version: "1.2.1",
          verified_consumers: ["metro@0.87.0"],
          reason: "test exception",
        }],
      },
    },
  };
  const report = {
    vulnerabilities: {
      "image-size": {
        severity: "high",
        via: [
          { url: "https://github.com/advisories/GHSA-w3rx-r6r6-pgpr", source: 1 },
          { url: "https://github.com/advisories/GHSA-5p2g-fcmc-qvqq", source: 2 },
        ],
        effects: ["metro"],
        fixAvailable: false,
      },
      metro: { severity: "high", via: ["image-size"], effects: [] },
    },
  };
  const mitigationReports = [{
    control_id: "mobile-image-size-build-only-v1",
    ok: true,
    project: "apps/mobile-client",
    finding_package: "image-size",
    package_version: "1.2.1",
    consumers: ["metro@0.87.0"],
  }];
  const allowedResult = evaluateAuditReport(report, policy, {
    project: "apps/mobile-client",
    asOf: "2026-08-26",
    mitigationReports,
  });
  assert.equal(allowedResult.ok, true);
  assert.equal(allowedResult.unresolved.length, 0);

  const breakingGraphReport = JSON.parse(JSON.stringify(report));
  breakingGraphReport.vulnerabilities["image-size"].fixAvailable = {
    name: "react-native",
    version: "0.86.3",
    isSemVerMajor: true,
  };
  const breakingGraphResult = evaluateAuditReport(breakingGraphReport, policy, {
    project: "apps/mobile-client",
    asOf: "2026-08-26",
    mitigationReports,
  });
  assert.equal(breakingGraphResult.ok, true);
  assert.equal(breakingGraphResult.unresolved.length, 0);

  const unsafeReport = {
    vulnerabilities: {
      "image-size": report.vulnerabilities["image-size"],
      "unexpected-package": { severity: "critical", via: [], effects: [] },
      "critical-through-metro": { severity: "critical", via: ["image-size"], effects: [] },
    },
  };
  const unsafeResult = evaluateAuditReport(unsafeReport, policy, {
    project: "apps/mobile-client",
    asOf: "2026-08-26",
    mitigationReports,
  });
  assert.equal(unsafeResult.ok, false);
  assert.equal(unsafeResult.unresolved[0].package, "unexpected-package");
  assert.equal(unsafeResult.unresolved[1].package, "critical-through-metro");

  const incompleteResult = evaluateAuditReport({ metadata: {} }, policy, {
    project: "apps/mobile-client",
    asOf: "2026-08-09",
  });
  assert.equal(incompleteResult.ok, false);
  assert.match(incompleteResult.errors[0], /missing a vulnerabilities object/);

  const unknownSeverityResult = evaluateAuditReport({
    vulnerabilities: {
      "malformed-severity": { severity: "severe", via: [], effects: [] },
    },
  }, policy, {
    project: "apps/mobile-client",
    asOf: "2026-08-09",
  });
  assert.equal(unknownSeverityResult.ok, false);
  assert.match(unknownSeverityResult.errors[0], /unknown severity: severe/);

  const uppercaseSeverityResult = evaluateAuditReport({
    vulnerabilities: {
      "uppercase-critical": { severity: "CRITICAL", via: [], effects: [] },
    },
  }, policy, {
    project: "apps/mobile-client",
    asOf: "2026-08-09",
  });
  assert.equal(uppercaseSeverityResult.high_or_critical_findings, 1);
  assert.equal(uppercaseSeverityResult.unresolved[0].severity, "critical");

  const newlyFixableReport = JSON.parse(JSON.stringify(report));
  newlyFixableReport.vulnerabilities["image-size"].fixAvailable = {
    name: "image-size",
    version: "2.0.3",
    isSemVerMajor: false,
  };
  const newlyFixableResult = evaluateAuditReport(newlyFixableReport, policy, {
    project: "apps/mobile-client",
    asOf: "2026-08-26",
    mitigationReports,
  });
  assert.equal(newlyFixableResult.ok, false);
  assert.match(newlyFixableResult.errors[0], /reviewed breaking graph remediation/);

  const missingMitigationResult = evaluateAuditReport(report, policy, {
    project: "apps/mobile-client",
    asOf: "2026-08-26",
  });
  assert.equal(missingMitigationResult.ok, false);
  assert.match(missingMitigationResult.errors[0], /lacks passing mitigation evidence/);

  const changedConsumerResult = evaluateAuditReport(report, policy, {
    project: "apps/mobile-client",
    asOf: "2026-08-26",
    mitigationReports: [{ ...mitigationReports[0], consumers: ["metro@0.88.0"] }],
  });
  assert.equal(changedConsumerResult.ok, false);
  assert.match(changedConsumerResult.errors[0], /unreviewed consumers/);
  console.log("Node audit policy self-test passed");
}

function parseArguments(argv) {
  const args = {};
  for (let index = 0; index < argv.length; index += 1) {
    const value = argv[index];
    if (value === "--self-test") {
      args.selfTest = true;
    } else if (value.startsWith("--") && argv[index + 1]) {
      args[value.slice(2)] = argv[index + 1];
      index += 1;
    }
  }
  return args;
}

if (require.main === module) {
  const args = parseArguments(process.argv.slice(2));
  if (args.selfTest) {
    runSelfTest();
    process.exit(0);
  }
  if (!args.report || !args.policy || !args.project) {
    console.error("usage: node tools/check_node_audit_policy.cjs --report REPORT --policy POLICY --project PROJECT");
    process.exit(2);
  }

  const mitigationReports = args["mitigation-report"] ? [readJson(args["mitigation-report"])] : [];
  const result = evaluateAuditReport(readJson(args.report), readJson(args.policy), {
    project: args.project,
    mitigationReports,
  });
  console.log(JSON.stringify(result, null, 2));
  process.exit(result.ok ? 0 : 1);
}

module.exports = { evaluateAuditReport };
