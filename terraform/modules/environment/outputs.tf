output "namespace" {
  description = "Namespace created for this environment."
  value       = kubernetes_namespace_v1.this.metadata[0].name
}

output "redis_secret_name" {
  description = "Secret holding the generated Redis password (key: password)."
  value       = kubernetes_secret_v1.redis_auth.metadata[0].name
}

output "quota" {
  description = "Effective ResourceQuota hard limits."
  value       = kubernetes_resource_quota_v1.this.spec[0].hard
}

output "network_policies" {
  description = "Names of NetworkPolicies applied to the namespace."
  value = concat(
    [for p in kubernetes_network_policy_v1.default_deny : p.metadata[0].name],
    [for p in kubernetes_network_policy_v1.gateway : p.metadata[0].name],
    [for p in values(kubernetes_network_policy_v1.backends) : p.metadata[0].name],
    [for p in kubernetes_network_policy_v1.redis : p.metadata[0].name],
  )
}
