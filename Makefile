# FleetSync workflow shortcuts. Everything heavy is delegated to Ansible so the
# same steps run identically from a laptop or a CI runner.

ENV          ?= dev
CONTEXT      ?= fleetsync
IMAGE_TAG    ?= 1.0.0
PYTHON       ?= python3
VENV         ?= .venv
FLEETSYNC_URL ?= http://localhost:8080
SERVICES     := registry telemetry gateway

ANSIBLE := cd ansible && ansible-playbook

.PHONY: help venv unit-test functional-test perf-test compose-up compose-down \
        galaxy bootstrap deploy verify loadtest port-forward hpa-watch teardown destroy \
        tf-plan kustomize-render

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------- local dev

venv: ## Create a virtualenv with all service + test dependencies
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/pip install -q -r services/registry/requirements-dev.txt \
		-r services/telemetry/requirements-dev.txt \
		-r services/gateway/requirements-dev.txt \
		-r tests/requirements.txt

unit-test: ## Run unit tests for every service
	@for svc in $(SERVICES); do \
		echo "==> $$svc"; \
		(cd services/$$svc && ../../$(VENV)/bin/pytest -q) || exit 1; \
	done

compose-up: ## Run the whole stack locally with docker compose
	docker compose up --build -d

compose-down: ## Stop the docker compose stack
	docker compose down -v

# ---------------------------------------------------------------- cluster

galaxy: ## Install required Ansible collections
	cd ansible && ansible-galaxy collection install -r requirements.yml

bootstrap: galaxy ## Install tools, start Minikube, apply Terraform, build, deploy and smoke-test
	$(ANSIBLE) site.yml -e image_tag=$(IMAGE_TAG)

deploy: ## Rebuild images and redeploy onto the running cluster
	$(ANSIBLE) deploy.yml -e image_tag=$(IMAGE_TAG)

verify: ## Run the in-cluster smoke test only
	$(ANSIBLE) site.yml --tags verify

tf-plan: ## Show the Terraform plan for the environments
	cd terraform && terraform init -input=false && terraform plan -var kube_context=$(CONTEXT)

kustomize-render: ## Render the manifests for ENV without applying them
	kubectl kustomize k8s/overlays/$(ENV)

port-forward: ## Expose ENV's gateway on localhost:8080
	scripts/port_forward.sh $(ENV) 8080

# ---------------------------------------------------------------- testing

functional-test: ## Run end-to-end tests against FLEETSYNC_URL (port-forward or compose)
	FLEETSYNC_URL=$(FLEETSYNC_URL) $(VENV)/bin/pytest -v tests/functional

perf-test: ## Run Locust from this machine against FLEETSYNC_URL (stepped ramp, ~8 min)
	mkdir -p results
	LOAD_SHAPE=step $(VENV)/bin/locust -f tests/performance/locustfile.py --host $(FLEETSYNC_URL) \
		--headless --csv results/locust-$(ENV) --html results/locust-$(ENV).html

hpa-watch: ## Record HPA replica counts for ENV (run alongside perf-test)
	$(PYTHON) scripts/hpa_watch.py --context $(CONTEXT) -n fleetsync-$(ENV) --duration 660 \
		--out results/hpa-$(ENV).csv --expect-scale-out telemetry

loadtest: ## In-cluster Locust run + HPA scale-out assertion via Ansible
	$(ANSIBLE) loadtest.yml -e loadtest_env=$(ENV)

# ---------------------------------------------------------------- cleanup

teardown: ## Delete workloads and Terraform-managed environments
	$(ANSIBLE) teardown.yml

destroy: ## teardown + delete the Minikube profile
	$(ANSIBLE) teardown.yml -e delete_cluster=true
