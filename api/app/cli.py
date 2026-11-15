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
from app.services.accounts import create_account, revoke_api_key, update_account
from app.timezones import InvalidServerTimeRule


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
    create.add_argument(
        "--server-time",
        help="how to read MT5 report times: 'ny_close' (NY+7h) or an IANA zone like Europe/Athens",
    )
    create.add_argument("--quiet", action="store_true", help="print only the API key")

    update = sub.add_parser("update-account", help="change settings on an existing account")
    update.add_argument("--account-id", type=int, required=True)
    update.add_argument("--server-time", help="'ny_close' or an IANA zone like Europe/Athens")
    update.add_argument("--currency")
    update.add_argument("--starting-balance", type=Decimal)

    revoke = sub.add_parser("revoke-api-key", help="revoke key(s) by their displayed prefix")
    revoke.add_argument("prefix", help='the part shown after creation, e.g. "ta_AbCdEf12"')
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    try:
        return _run(args)
    except InvalidServerTimeRule as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


def _run(args: argparse.Namespace) -> int:
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
                server_timezone=args.server_time,
            )
            if args.quiet:
                print(key)
            else:
                print(f"Created account #{account.id} ({account.label}) for {args.email}")
                print(f"API key (shown once, store it safely): {key}")
            return 0

        if args.command == "update-account":
            account = update_account(
                db,
                args.account_id,
                server_timezone=args.server_time,
                currency=args.currency,
                starting_balance=args.starting_balance,
            )
            if account is None:
                print(f"No account with id {args.account_id}", file=sys.stderr)
                return 1
            print(
                f"Account #{account.id} ({account.label}): server_time={account.server_timezone}, "
                f"currency={account.currency}, starting_balance={account.starting_balance}"
            )
            return 0

        revoked = revoke_api_key(db, args.prefix)
        print(f"Revoked {revoked} key(s)")
        return 0 if revoked else 1


if __name__ == "__main__":
    sys.exit(main())
