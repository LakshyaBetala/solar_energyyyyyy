"""People who can sign in. Run on the machine Solara runs on.

  python -m app.users list
  python -m app.users add <username> "<Full Name>" <viewer|operator|supervisor>
  python -m app.users passwd <username>
  python -m app.users remove <username>

Passwords are asked for on the keyboard (never on the command line) and stored as salted scrypt.
"""
import getpass, sys
from . import db, extract  # noqa: F401  (extract loads .env)
from .config import ROLES

MIN_PASSWORD = 10


def ask_password():
    pw = getpass.getpass("Password (10+ characters): ")
    if len(pw) < MIN_PASSWORD:
        sys.exit("too short")
    if pw != getpass.getpass("Again: "):
        sys.exit("the two passwords differ")
    return pw


def main(argv):
    cmd = argv[0] if argv else "list"
    if cmd == "list":
        for u in db.q("SELECT username, name, role FROM users ORDER BY role DESC, username"):
            print(f"  {u['username']:16s} {u['role']:11s} {u['name']}")
    elif cmd == "add" and len(argv) == 4:
        username, name, role = argv[1].strip().lower(), argv[2].strip(), argv[3]
        if role not in ROLES:
            sys.exit(f"role must be one of {', '.join(ROLES)}")
        if db.one("SELECT 1 FROM users WHERE username=?", (username,)):
            sys.exit(f"{username} already exists; use passwd to change the password")
        db.ex("INSERT INTO users(username,name,role,pw) VALUES(?,?,?,?)",
              (username, name, role, db.pwhash(ask_password())))
        db.audit("system", "system", "Added user", username, role)
        print(f"added {username} ({role})")
    elif cmd == "passwd" and len(argv) == 2:
        if not db.one("SELECT 1 FROM users WHERE username=?", (argv[1],)):
            sys.exit("no such user")
        db.ex("UPDATE users SET pw=? WHERE username=?", (db.pwhash(ask_password()), argv[1]))
        db.ex("DELETE FROM sessions WHERE username=?", (argv[1],))  # signs them out everywhere
        db.audit("system", "system", "Changed password", argv[1])
        print("password changed")
    elif cmd == "remove" and len(argv) == 2:
        db.ex("DELETE FROM sessions WHERE username=?", (argv[1],))
        db.ex("DELETE FROM users WHERE username=?", (argv[1],))
        db.audit("system", "system", "Removed user", argv[1])
        print("removed")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
