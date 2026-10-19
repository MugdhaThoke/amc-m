# Feedback Loop Production Deployment Checklist

## Database
- [ ] Add indexes on frequently queried fields
  - `response_feedback.response_id`
  - `response_feedback.created_at`
  - `unified_evaluation_records.repair, lifecycle_status` (composite)
  - `repair_proposals.status, confidence` (composite)
  - `repair_proposals.created_at`
- [ ] Configure connection pooling
  - SQLite/PostgreSQL: optimized connection limits
  - Neo4j: max 50 connections
- [ ] Set up daily backups
  - `unified_evaluation_records` table
  - `repair_proposals` table
  - `graph_mutations` table
- [ ] Configure backup retention: 30 days

## API
- [ ] Rate limiting: 10 req/min per user on `/api/feedback`
- [ ] Request timeout: 30s for feedback submission
- [ ] Enable CORS with whitelist
- [ ] Configure authentication (JWT + RBAC with roles: Analyst, Compliance Officer, Admin)
- [ ] Ensure `/api/governance/promote` is restricted to Admin & Compliance Officer roles

## Background Jobs
- [ ] TimeoutProcessor running (60s interval)
- [ ] FeedbackRetryService running (60s interval)
- [ ] BatchEvaluationConsumer running (300s interval)
- [ ] GovernanceBatchScheduler running (weekly Monday 9am)
- [ ] LifecycleManager auto-advance running (daily)

## Monitoring
- [ ] Prometheus `/metrics` endpoint exposed
- [ ] Pipeline metrics: `pipeline_duration_seconds`, `pipeline_errors_total`
- [ ] Feedback submission metrics: `feedback_submissions_total`
- [ ] Evaluation metrics: `evaluation_tier_executions`, `evaluation_duration_seconds`
- [ ] Repair proposal metrics: `repair_proposals_total`
- [ ] Lifecycle transitions: `lifecycle_transitions_total`
- [ ] Queue gauges: `pending_feedback_gauge`, `pending_evaluation_gauge`
- [ ] Alerts configured:
  - Pipeline error rate > 5%
  - Pending feedback backlog > 100
  - Batch evaluation latency > 60s
- [ ] PagerDuty / email integration for critical alerts

## Performance
- [ ] Shared context cache enabled for 1-hop Neo4j subgraphs (1h TTL)
- [ ] Few-shot examples cache enabled (24h TTL)
- [ ] Batch evaluation size tuned (target: < 30s per 25 records)
- [ ] Neo4j query optimization with parameterized Cypher
- [ ] FAISS vector store index loaded in memory

## Security
- [ ] CypherValidator deny-list active (blocks DROP/CREATE INDEX/CONSTRAINT, unrestricted DELETE)
- [ ] Protected compliance fields enforced (`confidence_level`, `source_authority`, `effective_date`, `compliance_flag`, `regulatory_tag`)
- [ ] Audit trail logging enabled for all canonical Neo4j mutations in `graph_mutations`
- [ ] Sensitive data scrubbed before ingestion and feedback processing

## Documentation & Operations
- [ ] API documentation up-to-date in Swagger (`/docs`)
- [ ] Runbook for common feedback pipeline failure scenarios
- [ ] Governance workflow review guidelines published
- [ ] Monitoring dashboard setup documented
