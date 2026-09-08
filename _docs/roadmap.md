# Chorum-murohc — Roadmap

> **Status:** Long-term possibilities; not in the current implementation scope.

## Product Feature Roadmap

> **Source:** Product-owner requirements and ideas.

### AI Photo Proof & Approval

- Children attach before/after photos as proof of chore completion
- AI judges whether the chore is done
- AI checks photo metadata (date taken, location) for validity
- AI notifies parents with its assessment
- Parents can enable auto-approval based on AI verdict

### Creature Change

- Children can switch creature line after signup
- Costs points (amount TBD)

### Skill / Tech Tree

- Unlockable abilities purchased with points
- Examples:
  - Interest rate boost
  - One-off 2x point bonus
  - 6-month immunity to a specific chore (e.g. dishwasher)
  - Generosity: ability to share/gift points to another user

### Cloud Hosting

- Deploy beyond local dev (VPS, free tier, or similar)

## Technical Evolution Roadmap

> **Source:** Suggested by the coding assistant. These are architectural and
> operational recommendations, not product-owner feature requirements.

### Containerised Runtime

- Package the React frontend and Django API as independently deployable
  containers.
- Add a separate background-worker container when asynchronous work is needed.
- Provide a local multi-container environment for production-like testing.

### Background Work and Caching

- Introduce Redis when shared caching or a distributed job queue is justified.
- Introduce Celery workers for scheduled interest processing, notifications,
  and image-processing jobs.
- Design background operations to be retryable and idempotent.

### Object Storage

- Move creature and user-uploaded images to S3-compatible object storage.
- Keep media storage independent from individual application containers.

### Routing and Scaling

- Place a reverse proxy or managed load balancer in front of deployed services.
- Keep Django application containers stateless so that instances can be scaled
  horizontally.
- Split the modular monolith into separate services only when scaling,
  reliability, ownership, or release requirements demonstrate a clear benefit.

### Observability

- Centralise structured application logs.
- Collect service and business metrics.
- Add distributed tracing as the system gains asynchronous or independently
  deployed components.

### Production Hardening

- Add health and readiness checks for every deployed component.
- Manage secrets outside source control and container images.
- Automate tests, security checks, builds, migrations, and deployments through
  CI/CD.
- Establish database and object-storage backup and recovery procedures.
- Add monitoring, alerting, rate limiting, and documented operational runbooks.

### Security Follow-ups

> **Source:** Residual risks accepted by the product owner when the T018 trust
> boundary and permission policy was approved on 2026-09-08. Each item is a
> required security todo with an owner, not a permanent exemption. Issue
> [#95](https://github.com/alexisdacquay/chorum-murohc/issues/95) must recheck
> every item independently before the campaign closes.

- [ ] Bounded login-abuse control: cap failed authentication attempts and delay
      or lock out repeat offenders. Owner:
      [#27](https://github.com/alexisdacquay/chorum-murohc/issues/27). Until it
      merges, credential guessing has no bounded control.
- [ ] Parent PIN retry limit, lockout, and recovery contract. Owner:
      [#29](https://github.com/alexisdacquay/chorum-murohc/issues/29). Until it
      merges, PIN management and approval mutations remain denied.
- [ ] Database-layer defence in depth for audit immutability and household
      isolation, including whether to adopt row-level security or tamper
      evidence. Application code alone enforces both today and privileged
      database access is trusted. Owner:
      [#123](https://github.com/alexisdacquay/chorum-murohc/issues/123).
- [ ] Second authentication factor or single sign-on. Session cookies are the
      only authentication factor today. No owner yet; adoption needs its own
      approved task.
- [ ] Independent human security review. The T018 policy was accepted by the
      product owner without a separate third-party reviewer, recorded in
      [issue #18](https://github.com/alexisdacquay/chorum-murohc/issues/18#issuecomment-5584623381).

### Optional Go or Rust Services

- Retain Python and Django for the core product.
- Consider Go for independently deployed concurrent services or workers only
  when there is a measured need.
- Consider Rust for CPU-intensive or unusually safety-critical components only
  when there is a measured need.
