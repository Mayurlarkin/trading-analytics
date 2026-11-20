"""Management commands (the first user and account are created here; the dashboard does the rest).

Examples:
    python -m app.cli create-account --email me@example.com --label "IFX Demo" --demo
    python -m app.cli update-account --account-id 1 --currency ZAR --starting-balance 100000
    python -m app.cli set-password --email me@example.com
    python -m app.cli update-user --email me@example.com --new-email me@gmail.com
    python -m app.cli stats --account-id 1
    python -m app.cli revoke-api-key ta_AbCdEf12
"""

import argparse
import getpass
import sys
from decimal import Decimal

from sqlalchemy.orm import Session

from app.analytics import by_instrument, by_session, by_weekday, summarize
from app.analytics.adapters import load_closed_trades
from app.analytics.text_report import format_groups, format_summary
from app.db import get_engine
from app.models import Account
from app.services.accounts import (
    DuplicateAccountLabel,
    EmailTaken,
    change_email,
    create_account,
    revoke_api_key,
    update_account,
)
from app.services.users import WeakPassword, set_password
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

    password = sub.add_parser("set-password", help="set the dashboard/API login password of a user")
    password.add_argument("--email", required=True)
    password.add_argument(
        "--password-stdin",
        action="store_true",
        help="read the password from standard input instead of asking (for scripts)",
    )

    user = sub.add_parser("update-user", help="change the login email of a user")
    user.add_argument("--email", required=True, help="the current email")
    user.add_argument("--new-email", required=True)

    stats = sub.add_parser("stats", help="print performance statistics for an account")
    stats.add_argument("--account-id", type=int, required=True)
    stats.add_argument(
        "--tz",
        default="America/New_York",
        help="clock for the weekday and session tables (default America/New_York)",
    )

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


def _print_stats(db: Session, account_id: int, tz: str) -> int:
    account = db.get(Account, account_id)
    if account is None:
        print(f"No account with id {account_id}", file=sys.stderr)
        return 1
    trades = load_closed_trades(db, account.id)
    if not trades:
        print(f"{account.label}: no trades yet.")
        return 0
    summary = summarize(trades, account.starting_balance)
    blocks = [
        format_summary(account.label, account.currency, summary),
        format_groups("Instrument", by_instrument(trades)),
        format_groups(f"Session ({tz})", by_session(trades, tz)),
        format_groups(f"Weekday ({tz})", by_weekday(trades, tz)),
    ]
    print("\n\n".join(blocks))
    if account.starting_balance <= 0:
        print("\nNote: this account has no starting balance, so drawdown percentages are "
              "meaningless. Set it with update-account --starting-balance.")  # fmt: skip
    return 0


def _set_password(db: Session, email: str, from_stdin: bool) -> int:
    if from_stdin:
        password = sys.stdin.readline().rstrip("\r\n")
    else:
        password = getpass.getpass("New password: ")
        if getpass.getpass("Repeat it: ") != password:
            print("The two passwords differ; nothing was changed.", file=sys.stderr)
            return 1
    try:
        found = set_password(db, email, password)
    except WeakPassword as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if not found:
        print(f"No user with email {email}. Create one with create-account first.", file=sys.stderr)
        return 1
    print(f"Password set for {email}. Log in at /docs with Authorize (username = the email).")
    return 0


def _run(args: argparse.Namespace) -> int:
    with Session(get_engine()) as db:
        if args.command == "create-account":
            try:
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
            except DuplicateAccountLabel as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 1
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

        if args.command == "update-user":
            try:
                user = change_email(db, args.email, args.new_email)
            except EmailTaken as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 1
            if user is None:
                print(f"No user with email {args.email}", file=sys.stderr)
                return 1
            print(f"Login email is now {user.email}")
            return 0

        if args.command == "set-password":
            return _set_password(db, args.email, args.password_stdin)

        if args.command == "stats":
            return _print_stats(db, args.account_id, args.tz)

        revoked = revoke_api_key(db, args.prefix)
        print(f"Revoked {revoked} key(s)")
        return 0 if revoked else 1


if __name__ == "__main__":
    sys.exit(main())
