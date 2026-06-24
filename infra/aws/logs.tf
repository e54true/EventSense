# One CloudWatch log group per service. 14-day retention keeps the log bill
# negligible while still covering a debugging window.

resource "aws_cloudwatch_log_group" "svc" {
  for_each = local.services

  name              = "/ecs/${local.name}/${each.key}"
  retention_in_days = 14

  tags = { Name = "${local.name}-${each.key}-logs" }
}
