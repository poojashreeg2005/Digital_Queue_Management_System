"""
rollback_visitor.py
Safe rollback script for the Parent & Visitor Assistance Module.
Drops ONLY the visitor module tables (visitor_tokens, visitor_instructions,
campus_notices, campus_locations, floor_plans, visitor_purposes).
Leaves all original 8 tables (users, departments, services, counters,
tokens, service_requests, notifications, payments) completely intact.
"""

import sys
from app import app
from models import (
    db, VisitorToken, VisitorInstruction,
    CampusNotice, CampusLocation, FloorPlan, VisitorPurpose
)


def run_rollback(confirm=False):
    if not confirm:
        print("WARNING: This will drop all visitor module tables.")
        print("To proceed, pass confirm=True or run with --confirm argument.")
        return

    print("=" * 65)
    print("QUEUEFLOW AI: VISITOR MODULE DATABASE ROLLBACK")
    print("=" * 65)

    with app.app_context():
        tables = [
            VisitorToken.__table__,
            VisitorInstruction.__table__,
            CampusNotice.__table__,
            CampusLocation.__table__,
            FloorPlan.__table__,
            VisitorPurpose.__table__,
        ]

        for table in tables:
            try:
                table.drop(db.engine, checkfirst=True)
                print(f"✓ Dropped table: {table.name}")
            except Exception as e:
                print(f"✗ Error dropping {table.name}: {e}")

        print("\nRollback complete. Original 8 tables remain completely untouched.")


if __name__ == "__main__":
    if "--confirm" in sys.argv:
        run_rollback(confirm=True)
    else:
        run_rollback(confirm=False)
