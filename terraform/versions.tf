terraform {
  required_version = ">= 1.5.0"

  required_providers {
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.35"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # Local state is fine for a Minikube lab. For a shared cluster swap this for a
  # remote backend (S3/GCS/Terraform Cloud) so state is locked and shared.
  backend "local" {
    path = "terraform.tfstate"
  }
}
