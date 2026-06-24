# Single ECR repository — all four services run the SAME image (exactly like
# Railway, where every service shares one Dockerfile and differs only by start
# command). CI builds once, pushes once; the four ECS task definitions just
# override the container command.

resource "aws_ecr_repository" "backend" {
  name                 = "${var.project_name}-backend"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true # free CVE scan on every push
  }

  tags = { Name = "${local.name}-ecr" }
}

# Keep only the 10 most recent images so untagged layers don't accrue storage cost.
resource "aws_ecr_lifecycle_policy" "backend" {
  repository = aws_ecr_repository.backend.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Expire all but the 10 most recent images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 10
      }
      action = { type = "expire" }
    }]
  })
}
