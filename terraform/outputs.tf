output "namespaces" {
  description = "Environment name -> namespace."
  value       = { for k, m in module.environment : k => m.namespace }
}

output "network_policies" {
  description = "Environment name -> NetworkPolicies applied."
  value       = { for k, m in module.environment : k => m.network_policies }
}

output "quotas" {
  description = "Environment name -> ResourceQuota hard limits."
  value       = { for k, m in module.environment : k => m.quota }
}
