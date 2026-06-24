# EventSense — AWS Infrastructure as Code (Milestone 13)
#
# Mirrors the Railway production topology on AWS primitives so we can tell a
# PaaS -> IaaS story: one Docker image, four long-running services (FastAPI +
# three Celery roles), a managed Postgres, and a managed Redis — but now with a
# VPC we own, IAM roles, Secrets Manager, and an ALB in front.
#
# M13 scope = author + `terraform validate` the config. It is intentionally NOT
# applied here; the real apply + data migration + DNS cutover is Milestone 14.

terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.60"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # Remote state lives in S3 with DynamoDB locking. Left as a partial config so
  # `terraform init -backend=false` works for validate without real AWS creds;
  # M14 will `init` with -backend-config pointing at the real bucket/table.
  #
  # backend "s3" {
  #   bucket         = "eventsense-tfstate"
  #   key            = "aws/terraform.tfstate"
  #   region         = "ap-northeast-1"
  #   dynamodb_table = "eventsense-tflock"
  #   encrypt        = true
  # }
}
