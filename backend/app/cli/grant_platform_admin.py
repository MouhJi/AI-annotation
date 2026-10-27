"""Grant/revoke platform access for an existing verified account; defaults to dry run."""
import argparse,json
from fastapi import HTTPException
from ..database import SessionLocal
from ..services.platform_admin import change_platform_role

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--email',required=True)
    parser.add_argument('--revoke',action='store_true')
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--confirm-email')
    args=parser.parse_args(); email=args.email.strip().casefold()
    if args.apply and (args.confirm_email or '').strip().casefold()!=email:
        parser.error('Apply requires --confirm-email matching --email')
    try:
        with SessionLocal() as db: result=change_platform_role(db,email,not args.revoke,args.apply)
    except (ValueError,HTTPException) as error: parser.error(str(error.detail) if isinstance(error,HTTPException) else str(error))
    print(json.dumps(result)); print('APPLIED' if args.apply else 'DRY RUN: no permissions changed')
if __name__=='__main__':main()
