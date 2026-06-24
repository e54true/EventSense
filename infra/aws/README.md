# EventSense on AWS — Terraform IaC (Milestone 13)

Infrastructure-as-Code that recreates EventSense's Railway production topology on
AWS primitives. This is the **IaaS half** of the PaaS→IaaS story: M9 shipped fast
on Railway (a PaaS) to prove the system works; M13 shows the same system
expressed as infrastructure we own and version-control.

> **Status: authored + `terraform validate`d, NOT applied.** Standing up the live
> stack, migrating data, and cutting DNS over is **Milestone 14**. Nothing here
> has touched a real AWS account, so the current spend is **$0**.

## What it provisions

| Railway today        | AWS equivalent here                                   |
|----------------------|-------------------------------------------------------|
| 4 services, 1 image  | 1 ECR repo + 4 ECS **Fargate** services (`local.services` + `for_each`) |
| `backend` (HTTP)     | ECS service behind a public **ALB** (`/api/v1/health` check) |
| `worker` / `analyzer`/ `beat` | 3 headless ECS services (no listener)        |
| Postgres plugin      | **RDS** PostgreSQL 16, private subnets                |
| Redis plugin         | **ElastiCache** Redis 7, private subnets              |
| Dashboard env vars   | **Secrets Manager**, injected via task `secrets`      |
| —                    | Hand-rolled **VPC**: 2 AZs, public/private subnets, 1 NAT GW |
| —                    | IAM execution/task roles, CloudWatch log groups, Container Insights |

The four services share one image and differ only by container `command` —
exactly the Railway/Procfile model, now driven by a single map so resizing or
adding a role is a one-line edit.

## Files

```
versions.tf        terraform + provider pins, (commented) S3 backend
providers.tf       aws provider + project-wide default_tags
variables.tf       region, sizing, secrets (sensitive)
network.tf         VPC, subnets, IGW, NAT, route tables
security_groups.tf alb → ecs → rds/redis least-privilege chain
ecr.tf             single image repo + lifecycle policy
rds.tf             Postgres + generated master password
elasticache.tf     single-node Redis
secrets.tf         Secrets Manager (DATABASE_URL/REDIS_URL assembled here)
iam.tf             execution role (pull/secrets/logs) + empty task role
alb.tf             ALB, target group, :80 listener
ecs.tf             cluster + task defs + services (for_each, dynamic LB block)
logs.tf            per-service CloudWatch log groups
outputs.tf         alb_dns_name, ecr_repository_url, endpoints
```

## Validate locally (no AWS account needed)

```bash
terraform fmt -recursive
terraform init -backend=false
terraform validate
```

`terraform plan`/`apply` additionally need real AWS credentials and the S3
backend uncommented — that's M14.

## Estimated monthly cost (ap-northeast-1, when applied in M14)

| Component                          | ~ USD/mo |
|------------------------------------|---------:|
| Fargate (1.5 vCPU + 3 GB, 24/7)    |      ~67 |
| NAT gateway (1×) + data            |      ~33 |
| Application Load Balancer          |      ~18 |
| RDS db.t4g.micro single-AZ + 20 GB |      ~16 |
| ElastiCache cache.t4g.micro        |      ~13 |
| ECR + Secrets + CloudWatch + egress|       ~5 |
| **Total**                          | **~150** |

**This is the whole point of the trade-off:** the identical workload costs
**~$15/mo on Railway vs ~$150/mo on AWS** (~10×). You don't move to AWS to save
money — you move for the VPC isolation, IAM, multi-AZ option, horizontal
scaling, and "infra as reviewable code" that a PaaS abstracts away. For a
side-project the PaaS wins on cost; the AWS build exists to demonstrate the
capability and to be ready when isolation/scale actually justify the bill.

## Deliberately simplified (prod-hardening backlog)

Kept off to stay cheap + apply-fast for a demo; each is a one-knob change:

- **RDS single-AZ** → `multi_az = true` for failover.
- **1 NAT gateway** (single point of egress failure) → one per AZ for HA.
- **HTTP-only ALB** → add a `:443` listener + ACM cert, redirect `:80→:443`.
- **NAT for all egress** → VPC endpoints (ECR/S3/Secrets/Logs) cut NAT data cost.
- **No autoscaling** → add `aws_appautoscaling_*` on the backend service.
- **`deletion_protection = false` / `skip_final_snapshot = true`** → flip for prod.
- **Fargate Spot** on `worker`/`analyzer` would shave ~$25/mo off the bill.
