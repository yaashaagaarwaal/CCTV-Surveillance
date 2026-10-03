"""Manage login accounts from the command line (useful on a headless server).

Run from the backend folder, with the virtualenv active:

    python scripts/manage_users.py list
    python scripts/manage_users.py add alice --role viewer
    python scripts/manage_users.py set-password admin
    python scripts/manage_users.py disable alice
    python scripts/manage_users.py enable alice
    python scripts/manage_users.py delete alice

Passwords are prompted for (never passed on the command line, where they would
end up in shell history) and must meet the password policy.
"""
import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.db.models import User  # noqa: E402
from app.db.session import SessionLocal, init_db  # noqa: E402
from app.security.passwords import hash_password, password_problems  # noqa: E402
from app.security.sessions import revoke_user_sessions  # noqa: E402


def ask_password(username: str) -> str:
    while True:
        first = getpass.getpass("New password: ")
        problems = password_problems(first, username)
        if problems:
            print("  Password " + "; ".join(problems))
            continue
        if first != getpass.getpass("Repeat password: "):
            print("  Passwords differ.")
            continue
        return first


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    add = sub.add_parser("add")
    add.add_argument("username")
    add.add_argument("--role", choices=["admin", "viewer"], default="viewer")
    for name in ("set-password", "disable", "enable", "delete"):
        sub.add_parser(name).add_argument("username")
    args = parser.parse_args()

    init_db()
    with SessionLocal() as db:
        if args.command == "list":
            for u in db.scalars(select(User).order_by(User.username)):
                print(f"{u.username:20} {u.role:8} {'DISABLED' if u.disabled else 'active'}")
            return 0

        username = args.username.strip().lower()
        user = db.scalar(select(User).where(User.username == username))
        if args.command == "add":
            if user:
                print(f"User '{username}' already exists.")
                return 1
            db.add(User(username=username, password_hash=hash_password(ask_password(username)), role=args.role))
        elif user is None:
            print(f"No such user '{username}'.")
            return 1
        elif args.command == "set-password":
            user.password_hash = hash_password(ask_password(username))
        elif args.command in ("disable", "enable"):
            user.disabled = args.command == "disable"
        elif args.command == "delete":
            revoke_user_sessions(user.id)
            db.delete(user)
        db.commit()
        if args.command in ("set-password", "disable", "delete") and user:
            revoke_user_sessions(user.id)  # force sign-out everywhere
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
