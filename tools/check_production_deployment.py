#!/usr/bin/env python3
"""Validate the provider-neutral read-only Kubernetes production contract."""

from __future__ import annotations

import argparse
from collections import Counter
import json
import re
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST_PATH = Path(
    "deploy/kubernetes/production-readonly/manifest.template.json"
)
DEFAULT_README_PATH = Path("deploy/kubernetes/production-readonly/README.md")
IMAGE_SENTINEL = (
    "registry.invalid/trading-bot/service@sha256:"
    "0000000000000000000000000000000000000000000000000000000000000000"
)
COMMIT_SENTINEL = "0000000000000000000000000000000000000000"
IMAGE_DIGEST_PATTERN = re.compile(r"[^@\s]+@sha256:[0-9a-f]{64}")
COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}")
DNS_LABEL_PATTERN = re.compile(r"[a-z0-9](?:[-a-z0-9]{0,251}[a-z0-9])?")
WORKLOAD_NAME = "trading-bot-readonly-api"
NAMESPACE = "trading-bot-readonly"


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Unable to load Kubernetes manifest {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _mapping(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _sequence(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _named_resource(resources: list[dict[str, Any]], kind: str) -> dict[str, Any]:
    matches = [
        item
        for item in resources
        if item.get("kind") == kind
        and _mapping(item.get("metadata")).get("name") in {WORKLOAD_NAME, NAMESPACE}
    ]
    return matches[0] if len(matches) == 1 else {}


def _named_entries(entries: object) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("name")): item
        for item in _sequence(entries)
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }


def validate_manifest(
    payload: dict[str, Any],
    *,
    require_rendered: bool = False,
    readme_text: str = "",
) -> dict[str, Any]:
    checks: dict[str, bool] = {}
    issues: list[str] = []

    def check(name: str, condition: object, message: str) -> None:
        passed = bool(condition)
        checks[name] = passed
        if not passed:
            issues.append(message)

    items = _sequence(payload.get("items"))
    resources = [item for item in items if isinstance(item, dict)]
    kinds = [str(item.get("kind") or "") for item in resources]
    expected_kinds = (
        "Namespace",
        "ServiceAccount",
        "Deployment",
        "Service",
        "PodDisruptionBudget",
        "HorizontalPodAutoscaler",
        "NetworkPolicy",
    )
    expected_api_versions = {
        "Namespace": "v1",
        "ServiceAccount": "v1",
        "Deployment": "apps/v1",
        "Service": "v1",
        "PodDisruptionBudget": "policy/v1",
        "HorizontalPodAutoscaler": "autoscaling/v2",
        "NetworkPolicy": "networking.k8s.io/v1",
    }
    check(
        "list_document",
        payload.get("apiVersion") == "v1" and payload.get("kind") == "List",
        "manifest must be a v1 List",
    )
    check(
        "exact_resource_set",
        Counter(kinds) == Counter(expected_kinds),
        "manifest must contain only the seven reviewed Kubernetes resources",
    )
    for kind in expected_kinds:
        check(
            f"one_{kind.lower()}",
            kinds.count(kind) == 1,
            f"manifest must contain exactly one {kind}",
        )
    check(
        "no_secret_objects",
        "Secret" not in kinds,
        "manifest must not embed a Kubernetes Secret",
    )
    check(
        "no_public_ingress",
        "Ingress" not in kinds,
        "TLS ingress must remain an explicit deployment-owned prerequisite",
    )
    check(
        "namespace_coherence",
        all(
            item.get("kind") == "Namespace"
            or _mapping(item.get("metadata")).get("namespace") == NAMESPACE
            for item in resources
        ),
        "every namespaced resource must stay in the dedicated read-only namespace",
    )
    check(
        "resource_identity",
        all(
            item.get("apiVersion")
            == expected_api_versions.get(str(item.get("kind") or ""))
            and _mapping(item.get("metadata")).get("name")
            == (NAMESPACE if item.get("kind") == "Namespace" else WORKLOAD_NAME)
            and (
                "namespace" not in _mapping(item.get("metadata"))
                if item.get("kind") == "Namespace"
                else _mapping(item.get("metadata")).get("namespace") == NAMESPACE
            )
            for item in resources
        ),
        "every resource must use the reviewed API version, name, and namespace",
    )

    namespace = _named_resource(resources, "Namespace")
    namespace_labels = _mapping(_mapping(namespace.get("metadata")).get("labels"))
    check(
        "restricted_namespace",
        all(
            namespace_labels.get(f"pod-security.kubernetes.io/{mode}") == "restricted"
            and namespace_labels.get(f"pod-security.kubernetes.io/{mode}-version")
            == "latest"
            for mode in ("enforce", "audit", "warn")
        ),
        "namespace must enforce, audit, and warn against the latest restricted Pod Security standard",
    )

    service_account = _named_resource(resources, "ServiceAccount")
    check(
        "service_account_token_disabled",
        service_account.get("automountServiceAccountToken") is False,
        "service account token automount must be disabled",
    )

    deployment = _named_resource(resources, "Deployment")
    deployment_spec = _mapping(deployment.get("spec"))
    template = _mapping(deployment_spec.get("template"))
    pod_spec = _mapping(template.get("spec"))
    containers = [
        item for item in _sequence(pod_spec.get("containers")) if isinstance(item, dict)
    ]
    container = containers[0] if len(containers) == 1 else {}
    expected_selector = {"app.kubernetes.io/name": WORKLOAD_NAME}
    check(
        "three_replicas",
        deployment_spec.get("replicas") == 3,
        "deployment must start with exactly three replicas",
    )
    check(
        "safe_rolling_update",
        _mapping(deployment_spec.get("strategy")).get("type") == "RollingUpdate"
        and _mapping(
            _mapping(deployment_spec.get("strategy")).get("rollingUpdate")
        ).get("maxUnavailable")
        == 0
        and _mapping(
            _mapping(deployment_spec.get("strategy")).get("rollingUpdate")
        ).get("maxSurge")
        == 1,
        "rolling updates must use maxUnavailable=0 and maxSurge=1",
    )
    check(
        "rollback_history",
        isinstance(deployment_spec.get("revisionHistoryLimit"), int)
        and int(deployment_spec.get("revisionHistoryLimit", 0)) >= 5,
        "deployment must retain at least five rollout revisions",
    )
    check(
        "readiness_stability",
        isinstance(deployment_spec.get("minReadySeconds"), int)
        and int(deployment_spec.get("minReadySeconds", 0)) >= 10,
        "deployment must require at least ten stable ready seconds",
    )
    check(
        "one_container",
        len(containers) == 1,
        "deployment must contain exactly one application container",
    )
    check(
        "no_auxiliary_containers",
        not _sequence(pod_spec.get("initContainers"))
        and not _sequence(pod_spec.get("ephemeralContainers")),
        "deployment must not add init or ephemeral containers with access to the token volume",
    )
    check(
        "deployment_selector_wiring",
        _mapping(deployment_spec.get("selector")).get("matchLabels")
        == expected_selector
        and all(
            _mapping(_mapping(template.get("metadata")).get("labels")).get(key) == value
            for key, value in expected_selector.items()
        ),
        "deployment selector and pod labels must remain aligned",
    )

    image = str(container.get("image") or "")
    image_is_digest = bool(IMAGE_DIGEST_PATTERN.fullmatch(image))
    if require_rendered:
        check(
            "immutable_rendered_image",
            image_is_digest
            and image != IMAGE_SENTINEL
            and not image.endswith("0" * 64),
            "rendered deployment image must use a non-placeholder sha256 digest",
        )
    else:
        check(
            "safe_image_sentinel",
            image == IMAGE_SENTINEL,
            "template must use the non-routable immutable image sentinel",
        )

    env = _named_entries(container.get("env"))
    env_values = {name: item.get("value") for name, item in env.items()}
    check(
        "environment_allowlist",
        len(_sequence(container.get("env"))) == 6
        and set(env)
        == {
            "BOT_SERVICE_API_READ_ONLY",
            "BOT_SERVICE_API_TRUST_PROXY_TLS",
            "BOT_SERVICE_API_TOKEN_FILE",
            "BOT_SERVICE_API_TOKEN_FILE_ALLOW_GROUP_READ",
            "BOT_SERVICE_API_MAX_REQUEST_BYTES",
            "TRADING_BOT_BUILD_COMMIT",
        },
        "observer deployment environment must contain only the reviewed read-only variables",
    )
    check(
        "api_read_only",
        env_values.get("BOT_SERVICE_API_READ_ONLY") == "1",
        "BOT_SERVICE_API_READ_ONLY must be 1",
    )
    check(
        "trusted_tls_proxy",
        env_values.get("BOT_SERVICE_API_TRUST_PROXY_TLS") == "1",
        "the cluster-only service must require a deployment-owned TLS proxy",
    )
    check(
        "token_file",
        env_values.get("BOT_SERVICE_API_TOKEN_FILE")
        == "/run/secrets/trading-bot/service-api-token"
        and env_values.get("BOT_SERVICE_API_TOKEN_FILE_ALLOW_GROUP_READ") == "1"
        and "BOT_SERVICE_API_TOKEN" not in env,
        "bearer authentication must use the reviewed group-readable mount and never an inline token",
    )
    commit = str(env_values.get("TRADING_BOT_BUILD_COMMIT") or "")
    deployment_commit = str(
        _mapping(_mapping(deployment.get("metadata")).get("annotations")).get(
            "trading-bot-build-commit"
        )
        or ""
    )
    pod_commit = str(
        _mapping(_mapping(template.get("metadata")).get("annotations")).get(
            "trading-bot-build-commit"
        )
        or ""
    )
    if require_rendered:
        commit_ok = bool(COMMIT_PATTERN.fullmatch(commit)) and commit != COMMIT_SENTINEL
        check(
            "rendered_commit_identity",
            commit_ok and deployment_commit == commit and pod_commit == commit,
            "rendered build commit must be a non-placeholder 40-character commit in env and annotations",
        )
    else:
        check(
            "commit_sentinel",
            commit == COMMIT_SENTINEL
            and deployment_commit == commit
            and pod_commit == commit,
            "template build commit sentinels must agree",
        )

    pod_security = _mapping(pod_spec.get("securityContext"))
    container_security = _mapping(container.get("securityContext"))
    check(
        "non_root_runtime",
        pod_security.get("runAsNonRoot") is True
        and pod_security.get("runAsUser") == 65532
        and pod_security.get("runAsGroup") == 65532
        and pod_security.get("fsGroup") == 65532
        and pod_security.get("fsGroupChangePolicy") == "OnRootMismatch"
        and pod_security.get("seccompProfile") == {"type": "RuntimeDefault"},
        "pod must run as non-root uid/gid/fsGroup 65532 with RuntimeDefault seccomp",
    )
    check(
        "restricted_container",
        container_security
        == {
            "allowPrivilegeEscalation": False,
            "readOnlyRootFilesystem": True,
            "runAsNonRoot": True,
            "capabilities": {"drop": ["ALL"]},
        },
        "container must disable privilege escalation, use a read-only root, and drop all capabilities",
    )
    check(
        "pod_identity_isolation",
        pod_spec.get("automountServiceAccountToken") is False
        and pod_spec.get("enableServiceLinks") is False
        and pod_spec.get("serviceAccountName") == WORKLOAD_NAME,
        "pod must disable token automount/service links and use the dedicated service account",
    )
    check(
        "host_namespace_isolation",
        pod_spec.get("hostNetwork") is not True
        and pod_spec.get("hostPID") is not True
        and pod_spec.get("hostIPC") is not True
        and pod_spec.get("shareProcessNamespace") is not True,
        "pod must not join host or shared process namespaces",
    )

    resources_spec = _mapping(container.get("resources"))
    requests = _mapping(resources_spec.get("requests"))
    limits = _mapping(resources_spec.get("limits"))
    check(
        "resource_bounds",
        requests == {"cpu": "250m", "memory": "256Mi", "ephemeral-storage": "256Mi"}
        and limits == {"cpu": "1", "memory": "1Gi", "ephemeral-storage": "512Mi"},
        "container must keep the reviewed CPU, memory, and ephemeral-storage bounds",
    )
    ports = _sequence(container.get("ports"))
    check(
        "container_runtime_contract",
        container.get("name") == "service-api"
        and container.get("imagePullPolicy") == "IfNotPresent"
        and "command" not in container
        and "args" not in container
        and ports == [{"name": "http", "containerPort": 8000, "protocol": "TCP"}],
        "container must use the reviewed image entrypoint and single HTTP port",
    )
    probes_ok = all(
        container.get(probe_name) == expected
        for probe_name, expected in {
            "startupProbe": {
                "httpGet": {"path": "/livez", "port": "http", "scheme": "HTTP"},
                "periodSeconds": 2,
                "timeoutSeconds": 2,
                "failureThreshold": 30,
            },
            "readinessProbe": {
                "httpGet": {"path": "/readyz", "port": "http", "scheme": "HTTP"},
                "periodSeconds": 5,
                "timeoutSeconds": 2,
                "failureThreshold": 3,
                "successThreshold": 1,
            },
            "livenessProbe": {
                "httpGet": {"path": "/livez", "port": "http", "scheme": "HTTP"},
                "periodSeconds": 10,
                "timeoutSeconds": 2,
                "failureThreshold": 3,
            },
        }.items()
    )
    check(
        "health_probes",
        probes_ok,
        "startup, readiness, and liveness HTTP probes must use the public health routes",
    )

    mounts = _named_entries(container.get("volumeMounts"))
    volumes = _named_entries(pod_spec.get("volumes"))
    token_secret = _mapping(
        _mapping(volumes.get("service-api-token", {})).get("secret")
    )
    token_secret_name = str(token_secret.get("secretName") or "")
    token_secret_name_ok = (
        bool(DNS_LABEL_PATTERN.fullmatch(token_secret_name))
        if require_rendered
        else token_secret_name == "trading-bot-service-api"
    )
    check(
        "secret_mount",
        mounts.get("service-api-token")
        == {
            "name": "service-api-token",
            "mountPath": "/run/secrets/trading-bot",
            "readOnly": True,
        }
        and token_secret_name_ok
        and token_secret.get("defaultMode") == 288
        and token_secret.get("items")
        == [{"key": "token", "path": "service-api-token", "mode": 288}]
        and token_secret.get("optional") is False,
        "service API token must come from the required read-only Kubernetes Secret volume",
    )
    check(
        "volume_allowlist",
        len(_sequence(pod_spec.get("volumes"))) == 3
        and len(_sequence(container.get("volumeMounts"))) == 3
        and set(volumes) == {"service-api-token", "runtime-state", "tmp"}
        and set(mounts) == {"service-api-token", "runtime-state", "tmp"}
        and mounts.get("runtime-state")
        == {"name": "runtime-state", "mountPath": "/home/nonroot/.trading-bot"}
        and mounts.get("tmp") == {"name": "tmp", "mountPath": "/tmp"},
        "pod must mount only the reviewed token, runtime-state, and tmp volumes",
    )
    check(
        "bounded_ephemeral_storage",
        volumes.get("runtime-state")
        == {"name": "runtime-state", "emptyDir": {"sizeLimit": "128Mi"}}
        and volumes.get("tmp")
        == {"name": "tmp", "emptyDir": {"medium": "Memory", "sizeLimit": "64Mi"}},
        "runtime and temporary writable storage must be explicitly bounded",
    )
    anti_affinity = _sequence(
        _mapping(_mapping(pod_spec.get("affinity")).get("podAntiAffinity")).get(
            "requiredDuringSchedulingIgnoredDuringExecution"
        )
    )
    expected_affinity_term = {
        "labelSelector": {"matchLabels": expected_selector},
        "topologyKey": "kubernetes.io/hostname",
    }
    expected_topology = [
        {
            "maxSkew": 1,
            "topologyKey": "topology.kubernetes.io/zone",
            "whenUnsatisfiable": "ScheduleAnyway",
            "labelSelector": {"matchLabels": expected_selector},
        },
        {
            "maxSkew": 1,
            "topologyKey": "kubernetes.io/hostname",
            "whenUnsatisfiable": "DoNotSchedule",
            "labelSelector": {"matchLabels": expected_selector},
        },
    ]
    check(
        "failure_domain_spread",
        anti_affinity == [expected_affinity_term]
        and pod_spec.get("topologySpreadConstraints") == expected_topology,
        "replicas must use required host anti-affinity and host/zone topology spreading",
    )

    service = _named_resource(resources, "Service")
    service_spec = _mapping(service.get("spec"))
    service_ports = _sequence(service_spec.get("ports"))
    check(
        "cluster_only_service",
        service_spec.get("type") == "ClusterIP"
        and service_spec.get("selector") == expected_selector
        and "externalIPs" not in service_spec
        and "externalName" not in service_spec
        and service_ports
        == [
            {
                "name": "http",
                "port": 80,
                "targetPort": "http",
                "protocol": "TCP",
                "appProtocol": "http",
            }
        ],
        "service must be cluster-only and target the named HTTP port",
    )

    pdb = _named_resource(resources, "PodDisruptionBudget")
    pdb_spec = _mapping(pdb.get("spec"))
    check(
        "disruption_budget",
        pdb_spec.get("minAvailable") == 2
        and _mapping(pdb_spec.get("selector")).get("matchLabels") == expected_selector,
        "PDB must keep two matching replicas available",
    )
    hpa = _named_resource(resources, "HorizontalPodAutoscaler")
    hpa_spec = _mapping(hpa.get("spec"))
    expected_hpa_behavior = {
        "scaleUp": {
            "stabilizationWindowSeconds": 0,
            "selectPolicy": "Max",
            "policies": [
                {"type": "Percent", "value": 100, "periodSeconds": 60},
                {"type": "Pods", "value": 4, "periodSeconds": 60},
            ],
        },
        "scaleDown": {
            "stabilizationWindowSeconds": 300,
            "selectPolicy": "Max",
            "policies": [{"type": "Percent", "value": 25, "periodSeconds": 60}],
        },
    }
    expected_hpa_metrics = [
        {
            "type": "Resource",
            "resource": {
                "name": "cpu",
                "target": {"type": "Utilization", "averageUtilization": 70},
            },
        },
        {
            "type": "Resource",
            "resource": {
                "name": "memory",
                "target": {"type": "Utilization", "averageUtilization": 75},
            },
        },
    ]
    check(
        "bounded_autoscaling",
        hpa_spec.get("minReplicas") == 3
        and hpa_spec.get("maxReplicas") == 10
        and _mapping(hpa_spec.get("scaleTargetRef"))
        == {"apiVersion": "apps/v1", "kind": "Deployment", "name": WORKLOAD_NAME}
        and hpa_spec.get("behavior") == expected_hpa_behavior
        and hpa_spec.get("metrics") == expected_hpa_metrics,
        "HPA must retain three replicas, cap at ten, use CPU/memory, and stabilize scale-down",
    )

    network_policy = _named_resource(resources, "NetworkPolicy")
    network_spec = _mapping(network_policy.get("spec"))
    expected_ingress = [
        {
            "from": [
                {
                    "namespaceSelector": {
                        "matchLabels": {"trading-bot-ingress-access": "true"}
                    },
                    "podSelector": {
                        "matchLabels": {"trading-bot-ingress-client": "true"}
                    },
                }
            ],
            "ports": [{"protocol": "TCP", "port": 8000}],
        },
        {
            "from": [
                {
                    "namespaceSelector": {
                        "matchLabels": {"trading-bot-monitoring-access": "true"}
                    },
                    "podSelector": {
                        "matchLabels": {"trading-bot-monitoring-client": "true"}
                    },
                }
            ],
            "ports": [{"protocol": "TCP", "port": 8000}],
        },
    ]
    check(
        "default_deny_network",
        set(_sequence(network_spec.get("policyTypes"))) == {"Ingress", "Egress"}
        and _mapping(network_spec.get("podSelector")).get("matchLabels")
        == expected_selector
        and network_spec.get("ingress") == expected_ingress
        and network_spec.get("egress") == [],
        "NetworkPolicy must cover ingress and egress and deny all egress",
    )
    check(
        "explicit_ingress_clients",
        network_spec.get("ingress") == expected_ingress,
        "ingress must require explicit namespace and pod labels for proxy and monitoring clients",
    )

    if readme_text:
        normalized_readme = " ".join(readme_text.lower().split())
        check(
            "scope_documented",
            "does not provide high availability for trading execution"
            in normalized_readme
            and "tls-terminating ingress" in normalized_readme
            and "rollout undo" in normalized_readme
            and "at least 32 characters" in normalized_readme,
            "deployment README must state execution limits, TLS, rollback, and token prerequisites",
        )

    return {
        "ok": not issues,
        "mode": "rendered" if require_rendered else "template",
        "declared_scope": "stateless-read-only-service-api",
        "trading_execution_ha_claimed": False,
        "checks": checks,
        "issues": issues,
    }


def audit_manifest(path: Path, *, require_rendered: bool = False) -> dict[str, Any]:
    payload = load_manifest(path)
    readme_text = ""
    if not require_rendered:
        readme_path = REPO_ROOT / DEFAULT_README_PATH
        try:
            readme_text = readme_path.read_text(encoding="utf-8")
        except OSError as exc:
            return {
                "ok": False,
                "mode": "template",
                "declared_scope": "stateless-read-only-service-api",
                "trading_execution_ha_claimed": False,
                "checks": {"scope_documented": False},
                "issues": [f"Unable to read deployment README: {exc}"],
            }
    report = validate_manifest(
        payload, require_rendered=require_rendered, readme_text=readme_text
    )
    report["manifest"] = str(path)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest", type=Path, default=REPO_ROOT / DEFAULT_MANIFEST_PATH
    )
    parser.add_argument("--require-rendered", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = audit_manifest(args.manifest, require_rendered=args.require_rendered)
    except ValueError as exc:
        report = {"ok": False, "issues": [str(exc)]}
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(
            f"Production deployment contract: {'passed' if report.get('ok') else 'failed'}"
        )
        for issue in report.get("issues", []):
            print(f"- {issue}")
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
