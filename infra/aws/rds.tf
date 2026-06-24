# Managed PostgreSQL — the Railway Postgres plugin's AWS counterpart.
# Single-AZ + 7-day backups for the demo. Prod knobs left off on purpose
# (multi_az, deletion_protection, performance insights) — see README.

resource "random_password" "db" {
  length = 32
  # URL-safe symbol set only: the password is embedded into the DATABASE_URL
  # secret below, so chars with URL meaning (':', '@', '/', '?', '#', '&')
  # are excluded to avoid corrupting the connection string.
  override_special = "-_=+."
}

resource "aws_db_subnet_group" "main" {
  name       = "${local.name}-db-subnets"
  subnet_ids = aws_subnet.private[*].id
  tags       = { Name = "${local.name}-db-subnets" }
}

resource "aws_db_instance" "main" {
  identifier     = "${local.name}-pg"
  engine         = "postgres"
  engine_version = var.db_engine_version
  instance_class = var.db_instance_class

  allocated_storage     = var.db_allocated_storage
  max_allocated_storage = var.db_allocated_storage * 3 # storage autoscaling ceiling
  storage_type          = "gp3"
  storage_encrypted     = true

  db_name  = var.project_name
  username = var.db_username
  password = random_password.db.result
  port     = 5432

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  publicly_accessible    = false

  multi_az                = false # demo: single-AZ to halve the bill
  backup_retention_period = 7
  skip_final_snapshot     = true # demo convenience; flip to false for prod
  deletion_protection     = false
  apply_immediately       = true

  tags = { Name = "${local.name}-pg" }
}
