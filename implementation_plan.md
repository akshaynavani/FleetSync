# FleetSync — Implementation Plan

**FleetSync | Containerized Microservices Deployment**

A containerized multi-service fleet-management application deployed to Kubernetes (Minikube),
with Terraform provisioning the per-environment cluster infrastructure, Ansible automating host
configuration and the full deploy lifecycle, functional + performance test suites, and
Horizontal Pod Autoscaling to simulate fleet-scale load across isolated virtual environments.

## Key technical decisions

| Area | Decision |
|------|----------|
| Services | Three Python 3.12 / FastAPI microservices: `gateway`, `registry`, `telemetry`, backed by Redis |
| Containers | Multi-stage Dockerfiles, non-root user, healthchecks; `docker-compose.yml` for local dev |
| Orchestration | Kubernetes on Minikube, plain manifests composed with **Kustomize** (built into `kubectl`) — **no Helm** |
| Autoscaling | `autoscaling/v2` HPA on CPU + memory for `gateway` and `telemetry`; metrics-server addon |
| IaC | Terraform `kubernetes` provider; reusable `environment` module (namespace, ResourceQuota, LimitRange, NetworkPolicies, generated Redis secret, env ConfigMap) instantiated for `dev` and `staging` |
| Config mgmt | Ansible roles: `prerequisites`, `minikube`, `images`, `terraform`, `deploy`, `verify`, `loadtest`; one `site.yml` drives everything |
| Testing | pytest unit tests per service (fakeredis / mocked HTTP), pytest end-to-end functional suite against the cluster, Locust performance test that triggers and records HPA scale-out |

## Domain

- **registry** — vehicle registry (CRUD, status transitions) stored in Redis hashes.
- **telemetry** — ingests per-vehicle telemetry (position, speed, fuel, engine temp), keeps a
  capped history in Redis, computes summaries, and exposes a CPU-heavy route-optimization
  endpoint (nearest-neighbour + 2-opt TSP) used to drive autoscaling.
- **gateway** — public entrypoint; validates vehicles against the registry before forwarding
  telemetry, aggregates a fleet overview, and proxies route planning.

---

## Phase 1 — Microservices & containers

Deliverables:
- Shared helper package (`fleetsync_common`): JSON logging, Prometheus metrics middleware, settings.
- `registry`, `telemetry`, `gateway` FastAPI apps with `/healthz`, `/readyz`, `/metrics`.
- Unit tests for each service.
- Multi-stage Dockerfiles and `docker-compose.yml` for local development.

Files: `services/common/**`, `services/registry/**`, `services/telemetry/**`,
`services/gateway/**`, `docker-compose.yml`

## Phase 2 — Kubernetes manifests (Kustomize, no Helm)

Deliverables:
- `k8s/base`: Deployments (probes, resources, security contexts, anti-affinity), Services,
  Redis StatefulSet + headless Service, Ingress, HPAs, PodDisruptionBudgets, ConfigMap.
- `k8s/overlays/dev` and `k8s/overlays/staging` with replica / resource / HPA patches.

Files: `k8s/base/*.yaml`, `k8s/overlays/{dev,staging}/*`

## Phase 3 — Terraform infrastructure

Deliverables:
- `terraform/modules/environment`: namespace, ResourceQuota sized for HPA max replicas,
  LimitRange defaults, default-deny + allow-list NetworkPolicies, random Redis password
  Secret, environment ConfigMap.
- Root module wiring `dev` and `staging` environments against the Minikube kube-context,
  with variables, outputs and an example `tfvars`.

Files: `terraform/*.tf`, `terraform/modules/environment/*.tf`, `terraform/terraform.tfvars.example`

## Phase 4 — Ansible automation

Deliverables:
- Inventory (`localhost` control node + optional remote VM group) and group vars.
- Roles: `prerequisites` (Docker, kubectl, minikube, terraform), `minikube` (profile start,
  Calico CNI, metrics-server + ingress addons), `images` (build into Minikube's Docker daemon),
  `terraform` (init/apply), `deploy` (kustomize apply + rollout wait), `verify` (smoke checks).
- Playbooks: `site.yml`, `deploy.yml`, `teardown.yml`.

Files: `ansible/**`

## Phase 5 — Functional & performance testing, autoscaling validation

Deliverables:
- `tests/functional`: pytest end-to-end suite against the deployed gateway.
- `tests/performance`: Locust scenario mixing telemetry ingest and route optimisation,
  plus an HPA watcher script that records replica counts during the run.
- Ansible `loadtest` role / `loadtest.yml` playbook to run the load test and report scale-out.
- `Makefile` tying the workflow together.

Files: `tests/**`, `scripts/*`, `ansible/roles/loadtest/**`, `ansible/loadtest.yml`, `Makefile`

## Wrap-up

- `.gitignore` (Python, Terraform state, env files, IDE files).
- `README.md` with architecture diagram, run and test instructions.
