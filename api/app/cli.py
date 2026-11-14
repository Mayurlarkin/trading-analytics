"""Management commands (no login system yet, so accounts and API keys are created here).

Examples:
    python -m app.cli create-account --email me@example.com --label "IFX Demo" --demo
    python -m app.cli revoke-api-key ta_AbCdEf12
"""

import argparse
import sys
from decimal import Decimal

from sqlalchemy.orm import Session

from app.db import get_engine
from app.services.accounts import create_account, revoke_api_key


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser(
        "create-account", help="create a user (if new), an account, and an API key"
    )
    create.add_argument("--email", required=True)
    create.add_argument("--label", required=True, help='e.g. "IFX Demo"')
    create.add_argument("--broker")
    create.add_argument("--currency", default="USD")
    create.add_argument("--starting-balance", type=Decimal, default=Decimal("0"))
    create.add_argument("--demo", action="store_true", help="mark as a demo account")
    create.add_argument("--quiet", action="store_true", help="print only the API key")

    revoke = sub.add_parser("revoke-api-key", help="revoke key(s) by their displayed prefix")
    revoke.add_argument("prefix", help='the part shown after creation, e.g. "ta_AbCdEf12"')
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    with Session(get_engine()) as db:
        if args.command == "create-account":
            account, key = create_account(
                db,
                email=args.email,
                label=args.label,
                broker=args.broker,
                currency=args.currency,
                starting_balance=args.starting_balance,
                is_demo=args.demo,
            )
            if args.quiet:
                print(key)
            else:
                print(f"Created account #{account.id} ({account.label}) for {args.email}")
                print(f"API key (shown once, store it safely): {key}")
            return 0

        revoked = revoke_api_key(db, args.prefix)
        print(f"Revoked {revoked} key(s)")
        return 0 if revoked else 1


if __name__ == "__main__":
    sys.exit(main())
