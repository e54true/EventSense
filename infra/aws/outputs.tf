output "alb_dns_name" {
  description = "Public hostname for the API. Point the frontend / a CNAME here."
  value       = aws_lb.main.dns_name
}

output "ecr_repository_url" {
  description = "Push the built image here, then deploy with image_tag."
  value       = aws_ecr_repository.backend.repository_url
}

output "rds_endpoint" {
  description = "Postgres endpoint (private — reachable only from inside the VPC)."
  value       = aws_db_instance.main.address
}

output "redis_endpoint" {
  description = "Redis endpoint (private)."
  value       = aws_elasticache_cluster.main.cache_nodes[0].address
}

output "ecs_cluster_name" {
  value = aws_ecs_cluster.main.name
}

output "vpc_id" {
  value = aws_vpc.main.id
}
