# Rollback (private preview)

## Application

1. Stop traffic to the platform deployment.
2. Deploy the previous container image or Python wheel.
3. If schema migrations moved forward, restore the database snapshot taken before upgrade
   (see `backup-restore.md`) or run forward-only fixes — down migrations are not shipped.

## Data

- Governance revisions are monotonic; do not delete rows manually unless restoring from backup.
- Replaying idempotent plan/run keys returns cached documents.

## Repository operations

Repository rollback remains a product concern (`specmint execute rollback` locally). The
platform fake executor does not automate GitHub rollback in this preview.
