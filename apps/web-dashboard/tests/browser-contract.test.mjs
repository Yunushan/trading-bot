import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { createServer } from "node:http";
import { mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const RESULT_ATTRIBUTE = "data-tb-browser-contract-result";

function parseArgs(argv) {
  const result = {
    browser: String(process.env.TB_BROWSER || process.env.BROWSER || "chrome").toLowerCase(),
    executable: String(process.env.TB_BROWSER_EXECUTABLE || ""),
  };
  for (const arg of argv) {
    if (arg.startsWith("--browser=")) {
      result.browser = arg.slice("--browser=".length).trim().toLowerCase();
    } else if (arg.startsWith("--executable=")) {
      result.executable = arg.slice("--executable=".length).trim();
    }
  }
  return result;
}

function pathCandidates(browser) {
  const candidates = [];
  if (process.platform === "win32") {
    const programFiles = [
      process.env.PROGRAMFILES,
      process.env["PROGRAMFILES(X86)"],
      process.env.LOCALAPPDATA,
    ].filter(Boolean);
    const relative =
      browser === "edge"
        ? path.join("Microsoft", "Edge", "Application", "msedge.exe")
        : path.join("Google", "Chrome", "Application", "chrome.exe");
    for (const base of programFiles) {
      candidates.push(path.join(base, relative));
    }
    candidates.push(browser === "edge" ? "msedge.exe" : "chrome.exe");
  } else if (process.platform === "darwin") {
    if (browser === "edge") {
      candidates.push("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge");
    } else {
      candidates.push("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome");
      candidates.push("/Applications/Chromium.app/Contents/MacOS/Chromium");
    }
  } else {
    candidates.push(
      browser === "edge" ? "microsoft-edge" : "google-chrome",
      browser === "edge" ? "microsoft-edge-stable" : "google-chrome-stable",
      browser === "edge" ? "edge" : "chromium",
      browser === "edge" ? "msedge" : "chromium-browser",
    );
  }
  return candidates;
}

function isExecutablePath(value) {
  return value.includes("/") || value.includes("\\") || /^[A-Za-z]:/.test(value);
}

function runProcess(command, args, options = {}) {
  return new Promise((resolve) => {
    const child = spawn(command, args, {
      cwd: options.cwd || ROOT,
      windowsHide: true,
    });
    let stdout = "";
    let stderr = "";
    const timeout = setTimeout(() => {
      child.kill();
    }, options.timeoutMs || 30000);
    child.stdout.on("data", (chunk) => {
      stdout += chunk.toString();
    });
    child.stderr.on("data", (chunk) => {
      stderr += chunk.toString();
    });
    child.on("error", (error) => {
      clearTimeout(timeout);
      resolve({ ok: false, returncode: null, stdout, stderr: `${stderr}${error.message}` });
    });
    child.on("close", (code) => {
      clearTimeout(timeout);
      resolve({ ok: code === 0, returncode: code, stdout, stderr });
    });
  });
}

async function commandExists(command) {
  if (isExecutablePath(command)) {
    const result = await runProcess(command, ["--version"], { timeoutMs: 10000 });
    return result.ok;
  }
  const lookup =
    process.platform === "win32"
      ? await runProcess("where.exe", [command], { timeoutMs: 10000 })
      : await runProcess("sh", ["-lc", `command -v ${command}`], { timeoutMs: 10000 });
  return lookup.ok;
}

async function resolveBrowserExecutable(browser, explicit) {
  const supported = new Set(["chrome", "edge"]);
  if (!supported.has(browser)) {
    throw new Error(`Unsupported browser ${browser}; supported browser contract targets are chrome and edge.`);
  }
  const candidates = explicit ? [explicit] : pathCandidates(browser);
  for (const candidate of candidates) {
    if (await commandExists(candidate)) {
      return candidate;
    }
  }
  throw new Error(`Could not find ${browser} executable. Tried: ${candidates.join(", ")}`);
}

async function runFirefoxBrowserContract(targetUrl) {
  let firefox;
  try {
    ({ firefox } = await import("playwright"));
  } catch (error) {
    throw new Error(
      `Firefox contract requires the pinned Playwright dependency. Run npm --prefix apps/web-dashboard ci first. ${error?.message || error}`,
    );
  }

  let browser;
  try {
    browser = await firefox.launch({ headless: true });
  } catch (error) {
    throw new Error(
      `Firefox contract requires the Playwright Firefox browser. Run npx --prefix apps/web-dashboard playwright install firefox first. ${error?.message || error}`,
    );
  }

  try {
    const page = await browser.newPage();
    await page.goto(targetUrl, { waitUntil: "networkidle" });
    const rawPayload = await page.locator("html").getAttribute(RESULT_ATTRIBUTE);
    if (!rawPayload) {
      throw new Error("Firefox browser contract did not produce a result payload.");
    }
    const payload = JSON.parse(decodeURIComponent(rawPayload));
    if (!payload.ok) {
      throw new Error(`Firefox browser contract failed in page: ${payload.error}`);
    }
    return {
      browser: "firefox",
      executable: "playwright-firefox",
      payload,
    };
  } finally {
    await browser.close();
  }
}

function harnessHtml() {
  return `<!doctype html>
<meta charset="utf-8">
<title>Trading Bot Web Dashboard Browser Contract</title>
<input id="base-url" value="">
<input id="api-token" value="">
<script type="module">
const tests = [];
function record(name) {
  tests.push(name);
}
function finish(payload) {
  document.documentElement.setAttribute("${RESULT_ATTRIBUTE}", encodeURIComponent(JSON.stringify(payload)));
}
try {
  const service = await import("/modules/service-contract.js");
  const stream = await import("/modules/stream.js");
  const stateModule = await import("/modules/state.js");

  if (service.SERVICE_API_BASE_PATH !== "/api/v1") {
    throw new Error("Unexpected service API base path");
  }
  if (service.serviceApiRoute("stream_dashboard") !== "/api/v1/stream/dashboard") {
    throw new Error("Dashboard stream route does not match service contract");
  }
  let rejected = false;
  try {
    service.serviceApiRoute("runtime/operational-preflight");
  } catch {
    rejected = true;
  }
  if (!rejected) {
    throw new Error("Stale route names must be rejected");
  }
  record("service API route contract");

  localStorage.clear();
  sessionStorage.clear();
  localStorage.setItem(
    stateModule.PERSISTED_STORAGE_KEY,
    JSON.stringify({ baseUrl: "http://127.0.0.1:8000", token: "legacy-token" }),
  );
  stateModule.readStoredConfig();
  if (stateModule.state.baseUrl !== "http://127.0.0.1:8000") {
    throw new Error("Stored base URL did not load");
  }
  const sessionPayload = JSON.parse(sessionStorage.getItem(stateModule.TOKEN_SESSION_STORAGE_KEY) || "{}");
  const persistedPayload = JSON.parse(localStorage.getItem(stateModule.PERSISTED_STORAGE_KEY) || "{}");
  if (sessionPayload.token !== "legacy-token" || "token" in persistedPayload) {
    throw new Error("Token did not migrate to session storage");
  }
  record("session-scoped token storage");

  stateModule.elements.baseUrl.value = "http://localhost:8000/";
  stateModule.elements.apiToken.value = "session-token";
  if (stateModule.normalizedBaseUrl() !== "http://localhost:8000") {
    throw new Error("Base URL normalization failed");
  }
  if (stateModule.authHeaders().Authorization !== "Bearer session-token") {
    throw new Error("Authorization header not generated from session token");
  }
  record("browser config helpers");

  const url = stream.buildDashboardStreamUrl("http://localhost:8000", "/api/v1/stream/dashboard", {
    log_limit: "30",
    interval_ms: "1000",
  });
  if (url !== "http://localhost:8000/api/v1/stream/dashboard?log_limit=30&interval_ms=1000") {
    throw new Error("Dashboard stream URL changed");
  }
  if (url.includes("token=")) {
    throw new Error("Stream URL must not include bearer token query params");
  }
  const event = stream.parseServerSentEvent('event: dashboard\\ndata: {"state":"ok"}');
  if (event.name !== "dashboard" || event.data !== '{"state":"ok"}') {
    throw new Error("SSE parser did not preserve dashboard event payload");
  }
  if (!stream.supportsDashboardStream()) {
    throw new Error("Browser stream primitives are unavailable");
  }
  record("browser stream helpers");

  finish({
    ok: true,
    tests,
    userAgent: navigator.userAgent,
    location: location.href,
  });
} catch (error) {
  finish({
    ok: false,
    tests,
    error: error?.stack || String(error),
    userAgent: navigator.userAgent,
    location: location.href,
  });
}
</script>`;
}

function contentType(filePath) {
  if (filePath.endsWith(".js")) {
    return "text/javascript; charset=utf-8";
  }
  if (filePath.endsWith(".css")) {
    return "text/css; charset=utf-8";
  }
  if (filePath.endsWith(".html")) {
    return "text/html; charset=utf-8";
  }
  return "text/plain; charset=utf-8";
}

async function serveDashboard() {
  const { readFile } = await import("node:fs/promises");
  const server = createServer(async (request, response) => {
    try {
      const url = new URL(request.url || "/", "http://127.0.0.1");
      if (url.pathname === "/__browser_contract_harness__.html") {
        response.writeHead(200, { "content-type": "text/html; charset=utf-8" });
        response.end(harnessHtml());
        return;
      }
      const relative = decodeURIComponent(url.pathname.replace(/^\/+/, ""));
      const target = path.resolve(ROOT, relative || "index.html");
      if (!target.startsWith(ROOT)) {
        response.writeHead(403);
        response.end("forbidden");
        return;
      }
      const body = await readFile(target);
      response.writeHead(200, { "content-type": contentType(target) });
      response.end(body);
    } catch (error) {
      response.writeHead(404, { "content-type": "text/plain; charset=utf-8" });
      response.end(String(error?.message || error));
    }
  });
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", resolve);
  });
  const address = server.address();
  assert.equal(typeof address, "object");
  return { server, port: address.port };
}

function parseBrowserResult(stdout) {
  const match = stdout.match(new RegExp(`${RESULT_ATTRIBUTE}="([^"]+)"`));
  if (!match) {
    throw new Error(`Browser output did not contain ${RESULT_ATTRIBUTE}. Output tail: ${stdout.slice(-1000)}`);
  }
  return JSON.parse(decodeURIComponent(match[1]));
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (!["chrome", "edge", "firefox"].includes(args.browser)) {
    throw new Error(`Unsupported browser ${args.browser}; supported browser contract targets are chrome, edge, and firefox.`);
  }
  const executable = args.browser === "firefox" ? "" : await resolveBrowserExecutable(args.browser, args.executable);
  const profileDir = await mkdtemp(path.join(os.tmpdir(), "trading-bot-web-dashboard-browser-"));
  const { server, port } = await serveDashboard();
  const targetUrl = `http://127.0.0.1:${port}/__browser_contract_harness__.html`;
  try {
    let browserResult;
    if (args.browser === "firefox") {
      browserResult = await runFirefoxBrowserContract(targetUrl);
    } else {
      const commandArgs = [
        "--headless=new",
        "--disable-gpu",
        "--disable-dev-shm-usage",
        "--no-first-run",
        "--virtual-time-budget=5000",
        `--user-data-dir=${profileDir}`,
        "--dump-dom",
        targetUrl,
      ];
      const result = await runProcess(executable, commandArgs, { timeoutMs: 30000 });
      if (!result.ok) {
        throw new Error(
          `${args.browser} browser contract failed to launch or exited non-zero (${result.returncode}). ${result.stderr}`,
        );
      }
      const payload = parseBrowserResult(result.stdout);
      if (!payload.ok) {
        throw new Error(`${args.browser} browser contract failed in page: ${payload.error}`);
      }
      browserResult = { browser: args.browser, executable, payload };
    }
    console.log(
      JSON.stringify(
        {
          ok: true,
          browser: browserResult.browser,
          executable: browserResult.executable,
          userAgent: browserResult.payload.userAgent,
          tests: browserResult.payload.tests,
          targetUrl,
        },
        null,
        2,
      ),
    );
  } finally {
    await new Promise((resolve) => server.close(resolve));
    await rm(profileDir, { recursive: true, force: true });
  }
}

main().catch((error) => {
  console.error(error?.stack || String(error));
  process.exitCode = 1;
});
