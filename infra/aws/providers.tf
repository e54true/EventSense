provider "aws" {
  region = var.region

  # Every resource gets these tags — makes cost allocation (Cost Explorer) and
  # "what is this and who owns it" trivial. Project-wide tags belong here, not
  # copy-pasted onto every resource.
  default_tags {
    tags = {
      Project     = "EventSense"
      Environment = var.environment
      ManagedBy   = "Terraform"
      Milestone   = "M13"
    }
  }
}

provider "random" {}
