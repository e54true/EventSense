# The heart of the migration. Railway ran four "services" off one image,
# differing only by start command. Here that becomes one ECR image + four ECS
# Fargate services driven by a single `local.services` map and for_each, so
# adding/resizing a role is a one-line change, not four copy-pasted blocks.

locals {
  image = "${aws_ecr_repository.backend.repository_url}:${var.image_tag}"

  # Non-secret runtime config, injected as plain env. Secrets come from the
  # `secrets` block below (Secrets Manager), never here.
  environment = [
    { name = "ENVIRONMENT", value = var.environment },
    { name = "LLM_DEFAULT_MODEL", value = var.llm_default_model },
    { name = "LLM_PREMIUM_MODEL", value = var.llm_premium_model },
    { name = "LLM_DAILY_COST_CAP_USD", value = tostring(var.llm_daily_cost_cap_usd) },
    { name = "SEC_USER_AGENT", value = var.sec_user_agent },
    { name = "DEFAULT_TICKERS", value = var.default_tickers },
  ]

  secrets = [
    for k, s in aws_secretsmanager_secret.app : { name = k, valueFrom = s.arn }
  ]

  # One map drives task definitions, services, and log groups. attach_lb marks
  # the only HTTP-facing role; the Celery trio runs headless.
  services = {
    backend = {
      command       = ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
      cpu           = "512"
      memory        = "1024"
      desired_count = 1
      attach_lb     = true
    }
    worker = {
      command       = ["sh", "-c", "celery -A app.workers.celery_app worker --loglevel=info -E -Q fetch_queue,validate_queue --concurrency=4"]
      cpu           = "256"
      memory        = "512"
      desired_count = 1
      attach_lb     = false
    }
    analyzer = {
      command       = ["sh", "-c", "celery -A app.workers.celery_app worker --loglevel=info -E -Q analyze_queue --concurrency=2"]
      cpu           = "512"
      memory        = "1024"
      desired_count = 1
      attach_lb     = false
    }
    beat = {
      # Single replica only — two beats would double-enqueue every schedule
      # (same hazard called out in docker-compose.yml).
      command       = ["sh", "-c", "celery -A app.workers.celery_app beat --loglevel=info"]
      cpu           = "256"
      memory        = "512"
      desired_count = 1
      attach_lb     = false
    }
  }
}

resource "aws_ecs_cluster" "main" {
  name = "${local.name}-cluster"

  # Container Insights ties into the Milestone 11 observability story — task
  # CPU/memory/network land in CloudWatch automatically.
  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = { Name = "${local.name}-cluster" }
}

resource "aws_ecs_task_definition" "svc" {
  for_each = local.services

  family                   = "${local.name}-${each.key}"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = each.value.cpu
  memory                   = each.value.memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  container_definitions = jsonencode([
    merge(
      {
        name        = each.key
        image       = local.image
        command     = each.value.command
        essential   = true
        environment = local.environment
        secrets     = local.secrets
        logConfiguration = {
          logDriver = "awslogs"
          options = {
            "awslogs-group"         = aws_cloudwatch_log_group.svc[each.key].name
            "awslogs-region"        = var.region
            "awslogs-stream-prefix" = each.key
          }
        }
      },
      # Only the HTTP-facing role publishes a port for the target group.
      each.value.attach_lb ? {
        portMappings = [{ containerPort = 8000, protocol = "tcp" }]
      } : {},
    )
  ])

  tags = { Name = "${local.name}-${each.key}" }
}

resource "aws_ecs_service" "svc" {
  for_each = local.services

  name            = each.key
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.svc[each.key].arn
  desired_count   = each.value.desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.ecs.id]
    assign_public_ip = false # private subnets; egress via NAT
  }

  dynamic "load_balancer" {
    for_each = each.value.attach_lb ? [1] : []
    content {
      target_group_arn = aws_lb_target_group.backend.arn
      container_name   = each.key
      container_port   = 8000
    }
  }

  # Give the API time to run migrations + boot before the ALB starts failing it.
  health_check_grace_period_seconds = each.value.attach_lb ? 60 : null

  # The listener must exist before the LB-attached service registers targets.
  depends_on = [aws_lb_listener.http]
}
