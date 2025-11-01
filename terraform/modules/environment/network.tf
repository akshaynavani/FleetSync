# Zero-trust networking inside each environment namespace:
#   * everything is denied by default,
#   * the gateway accepts traffic from anywhere (NodePort / ingress controller),
#   * registry and telemetry only accept traffic from the gateway,
#   * redis only accepts traffic from registry and telemetry.
# Requires a CNI that enforces NetworkPolicy (the Ansible role starts Minikube with Calico).

locals {
  policy_count = var.enable_network_policies ? 1 : 0
}

resource "kubernetes_network_policy_v1" "default_deny" {
  count = local.policy_count

  metadata {
    name      = "default-deny-ingress"
    namespace = kubernetes_namespace_v1.this.metadata[0].name
    labels    = local.labels
  }

  spec {
    pod_selector {}
    policy_types = ["Ingress"]
  }
}

resource "kubernetes_network_policy_v1" "gateway" {
  count = local.policy_count

  metadata {
    name      = "allow-gateway-ingress"
    namespace = kubernetes_namespace_v1.this.metadata[0].name
    labels    = local.labels
  }

  spec {
    pod_selector {
      match_labels = { "app.kubernetes.io/name" = "gateway" }
    }
    policy_types = ["Ingress"]

    ingress {
      ports {
        port     = "8080"
        protocol = "TCP"
      }
    }
  }
}

resource "kubernetes_network_policy_v1" "backends" {
  for_each = var.enable_network_policies ? { registry = "8000", telemetry = "8001" } : {}

  metadata {
    name      = "allow-${each.key}-from-gateway"
    namespace = kubernetes_namespace_v1.this.metadata[0].name
    labels    = local.labels
  }

  spec {
    pod_selector {
      match_labels = { "app.kubernetes.io/name" = each.key }
    }
    policy_types = ["Ingress"]

    ingress {
      from {
        pod_selector {
          match_labels = { "app.kubernetes.io/name" = "gateway" }
        }
      }
      ports {
        port     = each.value
        protocol = "TCP"
      }
    }
  }
}

resource "kubernetes_network_policy_v1" "redis" {
  count = local.policy_count

  metadata {
    name      = "allow-redis-from-backends"
    namespace = kubernetes_namespace_v1.this.metadata[0].name
    labels    = local.labels
  }

  spec {
    pod_selector {
      match_labels = { "app.kubernetes.io/name" = "redis" }
    }
    policy_types = ["Ingress"]

    ingress {
      from {
        pod_selector {
          match_expressions {
            key      = "app.kubernetes.io/name"
            operator = "In"
            values   = ["registry", "telemetry"]
          }
        }
      }
      ports {
        port     = "6379"
        protocol = "TCP"
      }
    }
  }
}
