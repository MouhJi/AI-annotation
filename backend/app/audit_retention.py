"""Operator-only audit retention. Keep >=365 days; dry-run unless explicitly confirmed."""
import argparse
from datetime import datetime, timedelta, timezone
from sqlalchemy import delete, func, select
from .database import SessionLocal
from .models import AuditLog
from .models.auth import utcnow

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before', required=True, help='UTC ISO date YYYY-MM-DD')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--confirm-before')
    args=parser.parse_args();cutoff=datetime.fromisoformat(args.before).replace(tzinfo=timezone.utc)
    if cutoff > utcnow()-timedelta(days=365): parser.error('Retention requires keeping at least 365 days')
    with SessionLocal() as db:
        condition=AuditLog.created_at < cutoff
        print('Audit records selected:',db.scalar(select(func.count()).select_from(AuditLog).where(condition)))
        if not args.apply: print('DRY RUN. No audit records deleted.');return
        if args.confirm_before!=args.before:parser.error('Apply requires matching --confirm-before')
        db.execute(delete(AuditLog).where(condition));db.commit();print('Applied audit retention.')

if __name__=='__main__':main()
