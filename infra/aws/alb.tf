# Public Application Load Balancer in front of the FastAPI service only.
# The three Celery services have no inbound listener (same as Railway, where
# only the backend service exposes a domain).

resource "aws_lb" "main" {
  name               = "${local.name}-alb"
  load_balancer_type = "application"
  internal           = false
  security_groups    = [aws_security_group.alb.id]
  subnets            = aws_subnet.public[*].id

  tags = { Name = "${local.name}-alb" }
}

resource "aws_lb_target_group" "backend" {
  name        = "${local.name}-backend-tg"
  port        = 8000
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "ip" # awsvpc/Fargate registers task ENIs by IP, not instance id

  # Reuse the app's liveness probe — the same /api/v1/health the Dockerfile
  # HEALTHCHECK and Railway already hit. Cheap, no DB call.
  health_check {
    path                = "/api/v1/health"
    matcher             = "200"
    interval            = 30
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }

  tags = { Name = "${local.name}-backend-tg" }
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
  port              = 80
  protocol          = "HTTP"

  # Demo terminates plain HTTP at the ALB. Prod: add an HTTPS (:443) listener
  # with an ACM cert and redirect :80 -> :443. Left out to avoid the
  # cert/DNS-validation dependency in an unapplied stack.
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.backend.arn
  }
}
