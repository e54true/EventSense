variable "region" {
  description = "AWS region. Tokyo is closest low-latency region to Taiwan."
  type        = string
  default     = "ap-northeast-1"
}

variable "environment" {
  description = "Deployment environment name (tags + resource name prefixes)."
  type        = string
  default     = "production"
}

variable "project_name" {
  description = "Short name used to prefix resource names."
  type        = string
  default     = "eventsense"
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC."
  type        = string
  default     = "10.20.0.0/16"
}

variable "az_count" {
  description = "How many AZs to spread subnets across. 2 is the ALB minimum."
  type        = number
  default     = 2
}

variable "image_tag" {
  description = "Container image tag to deploy (e.g. a git SHA). Pushed to the ECR repo this stack creates."
  type        = string
  default     = "latest"
}

# --- Data layer sizing (kept small + cheap for the demo; see README for the
#     prod-hardening knobs we deliberately left off). ---

variable "db_instance_class" {
  description = "RDS instance class. db.t4g.micro is Graviton + cheapest burstable."
  type        = string
  default     = "db.t4g.micro"
}

variable "db_allocated_storage" {
  description = "RDS storage in GB."
  type        = number
  default     = 20
}

variable "db_engine_version" {
  description = "PostgreSQL engine version (match local/Railway: 16.x)."
  type        = string
  default     = "16.4"
}

variable "db_username" {
  description = "Master DB username."
  type        = string
  default     = "eventsense"
}

variable "redis_node_type" {
  description = "ElastiCache node type."
  type        = string
  default     = "cache.t4g.micro"
}

# --- Application secrets. Passed in at apply time (M14), never committed.
#     They land in Secrets Manager and are injected into containers via the
#     task definition `secrets` block — not as plaintext env vars. ---

variable "openai_api_key" {
  description = "OpenAI API key for the analyzer."
  type        = string
  sensitive   = true
  default     = "" # set via TF_VAR_openai_api_key / tfvars at apply time
}

variable "fred_api_key" {
  description = "FRED API key for macro-series ingestion."
  type        = string
  sensitive   = true
  default     = ""
}

variable "sec_user_agent" {
  description = "Identifying User-Agent string SEC EDGAR requires."
  type        = string
  default     = "EventSense ops@example.com"
}

variable "llm_default_model" {
  type    = string
  default = "gpt-5-mini"
}

variable "llm_premium_model" {
  type    = string
  default = "gpt-5"
}

variable "llm_daily_cost_cap_usd" {
  type    = number
  default = 5.0
}

variable "default_tickers" {
  type    = string
  default = "NVDA,TSLA,AAPL,MSFT,GOOGL,META,AMZN,AVGO,BRK-B,LLY,SPY,QQQ"
}
