locals {
  namespace = "fleetsync-${var.name}"
  labels = merge(
    {
      "app.kubernetes.io/part-of"    = "fleetsync"
      "app.kubernetes.io/managed-by" = "terraform"
      "fleetsync.io/environment"     = var.name
    },
    var.labels,
  )
}

resource "kubernetes_namespace_v1" "this" {
  metadata {
    name   = local.namespace
    labels = local.labels
  }
}

# Hard ceiling on what one environment may consume, so a runaway HPA in one
# environment cannot starve the others sharing the Minikube node.
resource "kubernetes_resource_quota_v1" "this" {
  metadata {
    name      = "fleetsync-quota"
    namespace = kubernetes_namespace_v1.this.metadata[0].name
    labels    = local.labels
  }

  spec {
    hard = {
      "requests.cpu"           = var.quota.requests_cpu
      "requests.memory"        = var.quota.requests_memory
      "limits.cpu"             = var.quota.limits_cpu
      "limits.memory"          = var.quota.limits_memory
      "pods"                   = tostring(var.quota.pods)
      "persistentvolumeclaims" = tostring(var.quota.pvcs)
      "services.loadbalancers" = "0"
    }
  }
}

# With a quota on requests/limits, every container must declare them; the
# LimitRange fills in defaults for anything that does not.
resource "kubernetes_limit_range_v1" "this" {
  metadata {
    name      = "fleetsync-limits"
    namespace = kubernetes_namespace_v1.this.metadata[0].name
    labels    = local.labels
  }

  spec {
    limit {
      type = "Container"
      default_request = {
        cpu    = var.container_defaults.default_request_cpu
        memory = var.container_defaults.default_request_memory
      }
      default = {
        cpu    = var.container_defaults.default_limit_cpu
        memory = var.container_defaults.default_limit_memory
      }
      max = {
        cpu    = var.container_defaults.max_cpu
        memory = var.container_defaults.max_memory
      }
    }
  }
}

resource "random_password" "redis" {
  length  = 32
  special = false
}

resource "kubernetes_secret_v1" "redis_auth" {
  metadata {
    name      = "redis-auth"
    namespace = kubernetes_namespace_v1.this.metadata[0].name
    labels    = local.labels
  }

  type = "Opaque"
  data = {
    password = random_password.redis.result
  }
}

resource "kubernetes_config_map_v1" "environment" {
  metadata {
    name      = "fleetsync-environment"
    namespace = kubernetes_namespace_v1.this.metadata[0].name
    labels    = local.labels
  }

  data = merge(
    {
      ENVIRONMENT = var.name
      NAMESPACE   = local.namespace
    },
    var.settings,
  )
}
