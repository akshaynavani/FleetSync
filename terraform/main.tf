# FleetSync cluster infrastructure. One isolated "virtual environment" per entry in
# var.environments, each with its own namespace, quota, network policies and secrets.
# Application workloads are deployed on top with Kustomize (see ../k8s).

module "environment" {
  source   = "./modules/environment"
  for_each = var.environments

  name                    = each.key
  quota                   = each.value.quota
  settings                = each.value.settings
  enable_network_policies = var.enable_network_policies
}
