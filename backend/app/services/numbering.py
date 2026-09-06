"""Concurrency-safe document numbering.

Each sequence is a single row in number_sequences; allocating a number
locks that row (SELECT ... FOR UPDATE on PostgreSQL) inside the caller's
transaction, so two concurrent requests can never receive the same
invoice/quote/order number. SQLite (tests only) serialises writers.
"""

from sqlalchemy.orm import Session

from app.models import NumberSequence

SEQUENCES = {
    "quote": ("Q-", 10001),
    "order": ("SO-", 10001),
    "invoice": ("INV-", 10001),
    "payment": ("PAY-", 10001),
    "shipment": ("SHP-", 10001),
    "customer": ("CUST-", 1001),
}


def next_number(db: Session, name: str) -> str:
    prefix, start = SEQUENCES[name]
    row = db.query(NumberSequence).filter(NumberSequence.name == name).with_for_update().first()
    if row is None:
        row = NumberSequence(name=name, prefix=prefix, next_value=start)
        db.add(row)
        db.flush()
        row = db.query(NumberSequence).filter(NumberSequence.name == name).with_for_update().first()
    value = row.next_value
    row.next_value = value + 1
    db.flush()
    return f"{row.prefix}{value}"
