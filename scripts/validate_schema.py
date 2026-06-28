"""Validate that the DB schema matches the ORM models by running a dry-run
Alembic autogenerate check.

Usage: python scripts/validate_schema.py
"""

import sys
import subprocess


def main():
    result = subprocess.run(
        ["alembic", "check"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print("SCHEMA VALIDATION FAILED")
        print(result.stdout)
        print(result.stderr)
        sys.exit(1)

    print("Schema is up to date — no drift detected.")
    sys.exit(0)


if __name__ == "__main__":
    main()
