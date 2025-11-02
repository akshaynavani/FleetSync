variable "kubeconfig_path" {
  description = "Path to the kubeconfig that Minikube writes."
  type        = string
  default     = "~/.kube/config"
}

variable "kube_context" {
  description = "kubeconfig context to target (Minikube names it after the profile)."
  type        = string
  default     = "fleetsync"
}

variable "enable_network_policies" {
  description = "Create NetworkPolicies. Disable if the cluster CNI does not enforce them."
  type        = bool
  default     = true
}

variable "environments" {
  description = "Environments to provision, keyed by name. Each becomes namespace fleetsync-<name>."
  type = map(object({
    quota = object({
      requests_cpu    = string
      requests_memory = string
      limits_cpu      = string
      limits_memory   = string
      pods            = number
      pvcs            = number
    })
    settings = optional(map(string), {})
  }))

  # Quotas are sized from the Kustomize overlays: (HPA maxReplicas + 1 surge pod)
  # x per-pod requests/limits for each Deployment, plus Redis.
  default = {
    dev = {
      quota = {
        requests_cpu    = "3"
        requests_memory = "3Gi"
        limits_cpu      = "12"
        limits_memory   = "6Gi"
        pods            = 20
        pvcs            = 2
      }
      settings = { TIER = "development" }
    }
    staging = {
      quota = {
        requests_cpu    = "6"
        requests_memory = "6Gi"
        limits_cpu      = "24"
        limits_memory   = "12Gi"
        pods            = 40
        pvcs            = 2
      }
      settings = { TIER = "pre-production" }
    }
  }
}
