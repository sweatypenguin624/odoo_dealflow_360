import argparse
import json

from app.core.logging import configure_logging
from app.seed.builder import run_seed
from app.seed.data import DEMO_PASSWORD, USERS, CUSTOMER_USERS


def main() -> None:
    configure_logging()
    parser = argparse.ArgumentParser(description="Seed DealFlow360 with a realistic demo dataset")
    parser.add_argument("--fresh", action="store_true", help="wipe all data first (refused in production without --force)")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    stats = run_seed(fresh=args.fresh, force=args.force, seed=args.seed)
    print(json.dumps(stats, indent=2, default=str))
    if "skipped" not in stats:
        print("\nDemo credentials (password for all: %s)" % DEMO_PASSWORD)
        for email, name, role, team in USERS[:5] + USERS[12:13]:
            print(f"  {role:<14} {email:<40} {name}")
        for email, name, customer in CUSTOMER_USERS[:1]:
            print(f"  {'customer':<14} {email:<40} {name} ({customer})")


if __name__ == "__main__":
    main()
