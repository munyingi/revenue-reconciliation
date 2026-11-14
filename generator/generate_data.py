"""
Generate fake source data for a fictional Finnish online shop (Kuura Outdoor Oy)
with reconciliation flaws planted on purpose.

Three source systems, each with its own conventions:

  1. Shop / order system   -> data/raw/shop_orders.csv
     Timestamps are naive local Helsinki time. Order totals in EUR at the
     shop's catalogue FX rate. Refund approvals are written onto the order.

  2. Payment provider (PSP) -> data/raw/psp_payment_events.csv
     Webhook events in UTC. Settles foreign currency at its own FX rate.
     Sometimes delivers the same capture event twice.

  3. Refund system          -> data/raw/refunds.csv
     Separate tool used by customer service. Timestamps in UTC. Refunds are
     approved first and only processed (money leaves) days later.

Planted flaws
  - timezone_shift         orders near midnight at month boundaries
  - payment_timing_lag     Klarna / bank transfer captured days after the order
  - duplicate_payment      PSP sends the same capture event twice
  - refund_not_processed   refund approved in the shop, money not yet returned
  - refund_prior_period    refund paid out this month for last month's order
  - failed_payment         card declined / bank transfer never paid, order stays open
  - fx_difference          SEK / NOK orders settled at a different rate

The generator also writes dbt/seeds/answer_key.csv: the expected impact of each
flaw on the October gap, computed from what was planted (the cause), not from
the reconciliation rules. The dbt tests check the pipeline finds exactly this.
"""

from __future__ import annotations

import csv
import random
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

SEED = 42
HEL = ZoneInfo("Europe/Helsinki")
UTC = timezone.utc

FIRST_DAY = date(2026, 9, 1)
LAST_DAY = date(2026, 11, 10)
EXTRACT_CUTOFF_UTC = datetime(2026, 11, 10, 22, 0, tzinfo=UTC)  # Nov 11 00:00 Helsinki
RECON_MONTH = (2026, 10)

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
SEED_DIR = ROOT / "dbt" / "seeds"

CENT = Decimal("0.01")

# Local hour-of-day demand profile (Helsinki). Night hours are quiet but not empty,
# which is exactly what makes the midnight timezone problem real.
HOUR_WEIGHTS = [
    3, 2, 2, 1, 1, 1, 2, 4, 6, 7, 8, 8,
    9, 9, 8, 8, 8, 9, 10, 11, 11, 10, 8, 5,
]

COUNTRIES = [("FI", "EUR", 0.88), ("SE", "SEK", 0.07), ("NO", "NOK", 0.05)]
CATALOGUE_RATE = {"EUR": Decimal("1"), "SEK": Decimal("11.50"), "NOK": Decimal("11.80")}

PAYMENT_METHODS = [
    ("card", 0.62),
    ("mobilepay", 0.18),
    ("klarna_invoice", 0.12),
    ("bank_transfer", 0.08),
]
INSTANT_METHODS = {"card", "mobilepay"}

CARD_DECLINE_RATE = 0.018
BANK_TRANSFER_UNPAID_RATE = 0.25
DUPLICATE_EVENT_RATE = 0.006
REFUND_RATE = 0.065
MIDNIGHT_LAUNCH_ORDERS = 70


def money(x) -> Decimal:
    return Decimal(str(x)).quantize(CENT, rounding=ROUND_HALF_UP)


def iso(ts: datetime) -> str:
    return ts.strftime("%Y-%m-%d %H:%M:%S")


def daily_volume(d: date) -> float:
    base = 158.0
    if d.weekday() >= 5:
        base *= 1.15
    if date(2026, 10, 24) <= d <= date(2026, 10, 31):  # autumn sale, last week of October
        base *= 1.35
    return base


def weighted_choice(rng: random.Random, options):
    r = rng.random()
    acc = 0.0
    for value, w in options:
        acc += w
        if r <= acc:
            return value
    return options[-1][0]


@dataclass
class Order:
    order_id: int
    order_number: str
    created_local: datetime  # naive Helsinki wall clock
    created_utc: datetime
    country: str
    currency: str
    total_eur: Decimal
    total_local: Decimal
    payment_method: str
    status: str = "completed"
    refunded_eur: Decimal = Decimal("0.00")
    # ground truth, used only for the answer key
    payment_failed: bool = False
    captured_utc: datetime | None = None
    settled_eur: Decimal | None = None
    payment_id: str | None = None


@dataclass
class Refund:
    refund_id: str
    payment_id: str
    order_id: int
    amount_eur: Decimal
    requested_utc: datetime
    processed_utc: datetime | None
    reason: str


@dataclass
class Event:
    event_id: str
    payment_id: str
    merchant_reference: str
    event_type: str
    payment_method: str
    currency: str
    amount_local: Decimal
    settled_amount_eur: Decimal
    event_utc: datetime
    received_utc: datetime
    is_planted_duplicate: bool = False


def local_to_utc(rng: random.Random, local_naive: datetime) -> datetime:
    # During the DST fall-back hour (25 Oct 03:00-04:00) a wall-clock time happens twice.
    fold = rng.randint(0, 1)
    return local_naive.replace(tzinfo=HEL, fold=fold).astimezone(UTC)


def generate():
    rng = random.Random(SEED)
    orders: list[Order] = []
    events: list[Event] = []
    refunds: list[Refund] = []

    order_seq = 100000
    event_seq = 1
    pay_seq = 500000
    refund_seq = 9000

    d = FIRST_DAY
    while d <= LAST_DAY:
        n = max(0, int(rng.gauss(daily_volume(d), 12)))
        # "Autumn drop" campaign email goes out at 00:00 Helsinki on 1 October:
        # a burst of orders in the first hours, which are still 30 September in UTC.
        burst = MIDNIGHT_LAUNCH_ORDERS if d == date(2026, 10, 1) else 0
        for i in range(n + burst):
            if i >= n:
                hour = rng.choices([0, 1, 2], weights=[6, 3, 1])[0]
            else:
                hour = rng.choices(range(24), weights=HOUR_WEIGHTS)[0]
            local = datetime(d.year, d.month, d.day, hour, rng.randint(0, 59), rng.randint(0, 59))
            created_utc = local_to_utc(rng, local)
            if created_utc > EXTRACT_CUTOFF_UTC:
                continue

            country, currency = None, None
            r = rng.random()
            acc = 0.0
            for c, cur, w in COUNTRIES:
                acc += w
                if r <= acc:
                    country, currency = c, cur
                    break

            total_eur = money(min(max(rng.lognormvariate(5.30, 0.55), 19.0), 2400.0))
            total_local = money(total_eur * CATALOGUE_RATE[currency])
            method = weighted_choice(rng, PAYMENT_METHODS)

            order_seq += 1
            o = Order(
                order_id=order_seq,
                order_number=f"KO-{order_seq}",
                created_local=local,
                created_utc=created_utc,
                country=country,
                currency=currency,
                total_eur=total_eur,
                total_local=total_local,
                payment_method=method,
            )
            pay_seq += 1
            o.payment_id = f"pay_{pay_seq}"
            merchant_ref = f"ORD{order_seq:08d}"  # PSP reference format differs from the shop's

            # Provider FX: always slightly worse for the merchant than the catalogue rate
            if currency == "EUR":
                provider_rate = Decimal("1")
            else:
                provider_rate = CATALOGUE_RATE[currency] * (Decimal("1") + Decimal(str(round(rng.uniform(0.004, 0.015), 5))))
            settled = money(total_local / provider_rate)

            # ---- payment outcome ----
            failed = False
            if method in INSTANT_METHODS:
                event_utc = created_utc + timedelta(seconds=rng.randint(2, 90))
                if method == "card" and rng.random() < CARD_DECLINE_RATE:
                    failed = True
                    event_type = "payment.failed"
            elif method == "klarna_invoice":
                ship_days = rng.randint(1, 6)
                event_utc = (created_utc + timedelta(days=ship_days)).replace(
                    hour=rng.randint(6, 16), minute=rng.randint(0, 59), second=rng.randint(0, 59)
                )
            else:  # bank_transfer
                if rng.random() < BANK_TRANSFER_UNPAID_RATE:
                    failed = True
                    event_type = "payment.expired"
                    event_utc = created_utc + timedelta(days=7)
                else:
                    event_utc = (created_utc + timedelta(days=rng.randint(1, 5))).replace(
                        hour=rng.randint(5, 14), minute=rng.randint(0, 59), second=rng.randint(0, 59)
                    )
            if not failed:
                event_type = "payment.captured"

            if event_utc <= EXTRACT_CUTOFF_UTC:
                ev = Event(
                    event_id=f"evt_{event_seq:07d}",
                    payment_id=o.payment_id,
                    merchant_reference=merchant_ref,
                    event_type=event_type,
                    payment_method=method,
                    currency=currency,
                    amount_local=total_local,
                    settled_amount_eur=Decimal("0.00") if failed else settled,
                    event_utc=event_utc,
                    received_utc=event_utc + timedelta(seconds=rng.randint(1, 20)),
                )
                event_seq += 1
                events.append(ev)

                if failed:
                    o.payment_failed = True
                    o.status = "awaiting_payment"  # the bug: shop never cancels these
                else:
                    o.captured_utc = event_utc
                    o.settled_eur = settled
                    # Duplicate webhook delivery: new event id, same payment, same amount
                    if rng.random() < DUPLICATE_EVENT_RATE:
                        dup = Event(**{**ev.__dict__})
                        dup.event_id = f"evt_{event_seq:07d}"
                        dup.received_utc = ev.received_utc + timedelta(seconds=rng.randint(30, 600))
                        dup.is_planted_duplicate = True
                        event_seq += 1
                        events.append(dup)
            else:
                o.status = "awaiting_payment" if method == "bank_transfer" else "awaiting_capture"

            # ---- refunds (separate system) ----
            if o.captured_utc is not None and rng.random() < REFUND_RATE:
                requested = o.captured_utc + timedelta(days=rng.randint(2, 20), hours=rng.randint(0, 8))
                if requested <= EXTRACT_CUTOFF_UTC:
                    if rng.random() < 0.75:
                        amount = o.total_eur
                    else:
                        amount = money(o.total_eur * Decimal(str(round(rng.uniform(0.3, 0.7), 2))))
                    processed = requested + timedelta(days=rng.randint(1, 10), hours=rng.randint(0, 12))
                    if processed > EXTRACT_CUTOFF_UTC:
                        processed = None
                    refund_seq += 1
                    refunds.append(
                        Refund(
                            refund_id=f"RF-{refund_seq}",
                            payment_id=o.payment_id,
                            order_id=o.order_id,
                            amount_eur=amount,
                            requested_utc=requested,
                            processed_utc=processed,
                            reason=rng.choice(["wrong_size", "damaged", "changed_mind", "late_delivery"]),
                        )
                    )
                    o.refunded_eur += amount
                    o.status = "refunded" if amount == o.total_eur else "partially_refunded"

            orders.append(o)
        d += timedelta(days=1)

    return orders, events, refunds


def in_month(ts: datetime | None, ym=RECON_MONTH) -> bool:
    return ts is not None and (ts.year, ts.month) == ym


def answer_key(orders: list[Order], events: list[Event], refunds: list[Refund]):
    """Expected October impact of each planted flaw, derived from the cause."""
    key: dict[str, list] = defaultdict(lambda: [Decimal("0.00"), 0])

    def add(label, amount):
        if amount != 0:
            key[label][0] += amount
            key[label][1] += 1

    by_order = {o.order_id: o for o in orders}

    for o in orders:
        in_dash = in_month(o.created_local)
        in_cfo = in_month(o.captured_utc)
        if o.payment_failed:
            if in_dash:
                add("failed_payment", o.total_eur)
            continue
        if o.captured_utc is None:  # still pending at extract time
            if in_dash:
                add("payment_timing_lag", o.total_eur)
            continue
        if in_dash and in_cfo:
            add("fx_difference", o.total_eur - o.settled_eur)
        elif in_dash != in_cfo:
            # Cause: instant methods only cross a month boundary because of timezones;
            # delayed methods cross it because the money arrives days later.
            label = "timezone_shift" if o.payment_method in INSTANT_METHODS else "payment_timing_lag"
            add(label, o.total_eur if in_dash else -o.settled_eur)

    for e in events:
        if e.is_planted_duplicate and in_month(e.event_utc):
            add("duplicate_payment", -e.settled_amount_eur)

    for r in refunds:
        o = by_order[r.order_id]
        dash_nets_it = in_month(o.created_local)
        cfo_nets_it = in_month(r.processed_utc)
        if dash_nets_it and not cfo_nets_it:
            add("refund_not_yet_processed", -r.amount_eur)
        elif cfo_nets_it and not dash_nets_it:
            add("refund_prior_period_order", r.amount_eur)

    return key


def write_csv(path: Path, header: list[str], rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def main():
    orders, events, refunds = generate()

    write_csv(
        RAW_DIR / "shop_orders.csv",
        ["order_id", "order_number", "created_at", "customer_country", "currency",
         "order_total_local", "order_total_eur", "payment_method", "status", "refunded_amount_eur"],
        [
            [o.order_id, o.order_number, iso(o.created_local), o.country, o.currency,
             f"{o.total_local}", f"{o.total_eur}", o.payment_method, o.status, f"{o.refunded_eur}"]
            for o in orders
        ],
    )

    events_sorted = sorted(events, key=lambda e: (e.received_utc, e.event_id))
    write_csv(
        RAW_DIR / "psp_payment_events.csv",
        ["event_id", "payment_id", "merchant_reference", "event_type", "payment_method", "currency",
         "amount_local", "settled_amount_eur", "event_timestamp_utc", "received_at_utc"],
        [
            [e.event_id, e.payment_id, e.merchant_reference, e.event_type, e.payment_method, e.currency,
             f"{e.amount_local}", f"{e.settled_amount_eur}", iso(e.event_utc), iso(e.received_utc)]
            for e in events_sorted
        ],
    )

    write_csv(
        RAW_DIR / "refunds.csv",
        ["refund_id", "payment_id", "amount_eur", "reason", "requested_at_utc", "processed_at_utc", "status"],
        [
            [r.refund_id, r.payment_id, f"{r.amount_eur}", r.reason, iso(r.requested_utc),
             iso(r.processed_utc) if r.processed_utc else "", "processed" if r.processed_utc else "pending"]
            for r in refunds
        ],
    )

    key = answer_key(orders, events, refunds)
    write_csv(
        SEED_DIR / "answer_key.csv",
        ["difference_type", "expected_amount_eur", "expected_line_count"],
        [[k, f"{v[0]}", v[1]] for k, v in sorted(key.items())],
    )

    total = sum((v[0] for v in key.values()), Decimal("0"))
    print(f"orders={len(orders)} events={len(events)} refunds={len(refunds)}")
    for k, v in sorted(key.items()):
        print(f"  {k:28s} {v[0]:>12,.2f}  ({v[1]} lines)")
    print(f"  {'TOTAL expected gap':28s} {total:>12,.2f}")


if __name__ == "__main__":
    main()
