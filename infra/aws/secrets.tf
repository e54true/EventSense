# All sensitive config lives in Secrets Manager and is injected into containers
# via the task definition `secrets` block (valueFrom = secret ARN). This is the
# concrete security upgrade over Railway, where the same values sat as plaintext
# env vars in the dashboard. Containers receive them as env at runtime but they
# never appear in the task definition JSON, ECS console, or CloudWatch.
#
# DATABASE_URL / REDIS_URL are assembled here from the RDS + ElastiCache
# attributes so the app's connection strings are derived, not hand-copied.

locals {
  database_url = "postgresql+asyncpg://${var.db_username}:${random_password.db.result}@${aws_db_instance.main.address}:5432/${var.project_name}"
  redis_url    = "redis://${aws_elasticache_cluster.main.cache_nodes[0].address}:6379/0"

  secret_values = {
    DATABASE_URL   = local.database_url
    REDIS_URL      = local.redis_url
    OPENAI_API_KEY = var.openai_api_key
    FRED_API_KEY   = var.fred_api_key
  }
}

resource "aws_secretsmanager_secret" "app" {
  for_each = local.secret_values

  name = "${local.name}/${each.key}"
  tags = { Name = "${local.name}-${lower(each.key)}" }
}

resource "aws_secretsmanager_secret_version" "app" {
  for_each = local.secret_values

  secret_id     = aws_secretsmanager_secret.app[each.key].id
  secret_string = each.value
}
