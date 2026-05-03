const assert = require("node:assert/strict");

const {
  MOBILE_REQUIRED_ROUTE_NAMES,
  SERVICE_API_BASE_PATH,
  SERVICE_API_LEGACY_BASE_PATH,
  SERVICE_API_ROUTE_SUFFIXES,
  SERVICE_API_VERSION,
  serviceApiRoute,
} = require("../service-contract");

async function test(name, callback) {
  await callback();
  console.log(`ok - ${name}`);
}

async function main() {
  await test("service API contract exposes the canonical base paths", async () => {
    assert.equal(SERVICE_API_VERSION, "1.0.0");
    assert.equal(SERVICE_API_BASE_PATH, "/api/v1");
    assert.equal(SERVICE_API_LEGACY_BASE_PATH, "/api");
  });

  await test("mobile required route names resolve to versioned API paths", async () => {
    for (const routeName of MOBILE_REQUIRED_ROUTE_NAMES) {
      assert.equal(
        serviceApiRoute(routeName),
        `${SERVICE_API_BASE_PATH}${SERVICE_API_ROUTE_SUFFIXES[routeName]}`,
      );
    }
  });

  await test("route helper rejects stale or unknown route names", async () => {
    assert.throws(() => serviceApiRoute("runtime/operational-preflight"), /Unknown service API route/);
    assert.throws(() => serviceApiRoute("llm/providers"), /Unknown service API route/);
    assert.throws(() => serviceApiRoute("control/start"), /Unknown service API route/);
    assert.throws(() => serviceApiRoute("missing_route"), /Unknown service API route/);
  });
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
