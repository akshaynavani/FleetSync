variable "name" {
  description = "Environment name (dev, staging, ...). The namespace becomes fleetsync-<name>."
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,20}$", var.name))
    error_message = "Environment name must be lowercase alphanumeric/dashes, 2-21 chars."
  }
}

variable "labels" {
  description = "Extra labels applied to every object created for this environment."
  type        = map(string)
  default     = {}
}

variable "quota" {
  description = "ResourceQuota hard limits. Size these so the HPA maxReplicas fit."
  type = object({
    requests_cpu    = string
    requests_memory = string
    limits_cpu      = string
    limits_memory   = string
    pods            = number
    pvcs            = number
  })
}

variable "container_defaults" {
  description = "LimitRange defaults for containers that do not declare resources."
  type = object({
    default_request_cpu    = string
    default_request_memory = string
    default_limit_cpu      = string
    default_limit_memory   = string
    max_cpu                = string
    max_memory             = string
  })
  default = {
    default_request_cpu    = "100m"
    default_request_memory = "128Mi"
    default_limit_cpu      = "500m"
    default_limit_memory   = "256Mi"
    max_cpu                = "2"
    max_memory             = "1Gi"
  }
}

variable "enable_network_policies" {
  description = "Create default-deny + allow-list NetworkPolicies (needs a policy-enforcing CNI such as Calico)."
  type        = bool
  default     = true
}

variable "settings" {
  description = "Free-form key/values published in the fleetsync-environment ConfigMap."
  type        = map(string)
  default     = {}
}
