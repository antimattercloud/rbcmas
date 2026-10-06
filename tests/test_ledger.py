import pytest

from app.services.inventory_service import (
    InsufficientQuantityError,
    ReasonRequiredError,
    calculate_balance_sheet,
    decide_adjustment,
    record_physical_count,
    record_usage,
)


def test_receive_sets_expected_quantity(db, base_fixtures):
    container = base_fixtures["container"]
    assert container.expected_quantity == 500.0
    assert container.status == "AVAILABLE"


def test_usage_reduces_expected_quantity_and_creates_transaction(db, base_fixtures):
    container = base_fixtures["container"]
    researcher = base_fixtures["researcher"]

    txn = record_usage(db, container=container, quantity_used=100, user=researcher, purpose="Test")
    db.commit()

    assert container.expected_quantity == 400.0
    assert txn.transaction_type == "USE"
    assert txn.quantity_delta == -100
    assert txn.expected_quantity_before == 500.0
    assert txn.expected_quantity_after == 400.0


def test_usage_cannot_exceed_available_quantity(db, base_fixtures):
    container = base_fixtures["container"]
    researcher = base_fixtures["researcher"]

    with pytest.raises(InsufficientQuantityError):
        record_usage(db, container=container, quantity_used=10_000, user=researcher)

    db.refresh(container)
    assert container.expected_quantity == 500.0  # unchanged after the failed attempt


def test_physical_count_within_tolerance_needs_no_reason(db, base_fixtures):
    container = base_fixtures["container"]
    manager = base_fixtures["manager"]

    count, txn, adjustment = record_physical_count(db, container=container, physical_quantity=500.0, user=manager)
    db.commit()

    assert adjustment is None
    assert count.variance == 0
    assert txn.transaction_type == "PHYSICAL_COUNT"
    assert txn.quantity_delta == 0  # a checkpoint, never a silent overwrite
    assert container.expected_quantity == 500.0  # untouched


def test_physical_count_outside_tolerance_requires_reason(db, base_fixtures):
    container = base_fixtures["container"]
    manager = base_fixtures["manager"]

    with pytest.raises(ReasonRequiredError):
        record_physical_count(db, container=container, physical_quantity=400.0, user=manager)

    db.refresh(container)
    assert container.expected_quantity == 500.0  # never overwritten by a bare count


def test_physical_count_discrepancy_creates_pending_adjustment_and_decide_flow(db, base_fixtures):
    container = base_fixtures["container"]
    manager = base_fixtures["manager"]
    admin = base_fixtures["admin"]

    count, txn, adjustment = record_physical_count(
        db, container=container, physical_quantity=400.0, user=manager, reason="Spillage"
    )
    db.commit()

    assert adjustment is not None
    assert adjustment.approval_status == "PENDING"
    assert container.expected_quantity == 500.0  # still unchanged - pending approval only

    decide_adjustment(db, adjustment=adjustment, approve=True, approver=admin)
    db.commit()

    assert adjustment.approval_status == "APPROVED"
    assert container.expected_quantity == 400.0  # now applied via a real ADJUSTMENT transaction


def test_rejected_adjustment_does_not_change_quantity(db, base_fixtures):
    container = base_fixtures["container"]
    manager = base_fixtures["manager"]
    admin = base_fixtures["admin"]

    _, _, adjustment = record_physical_count(db, container=container, physical_quantity=100.0, user=manager, reason="Other")
    db.commit()

    decide_adjustment(db, adjustment=adjustment, approve=False, approver=admin)
    db.commit()

    assert adjustment.approval_status == "REJECTED"
    assert container.expected_quantity == 500.0  # rejected: no change applied


def test_balance_sheet_reconciles_after_use_and_approved_adjustment(db, base_fixtures):
    container = base_fixtures["container"]
    manager = base_fixtures["manager"]
    admin = base_fixtures["admin"]

    record_usage(db, container=container, quantity_used=50, user=manager)
    db.commit()
    assert container.expected_quantity == 450.0

    _, _, adjustment = record_physical_count(db, container=container, physical_quantity=430.0, user=manager, reason="Evaporation")
    db.commit()
    decide_adjustment(db, adjustment=adjustment, approve=True, approver=admin)
    db.commit()

    balance = calculate_balance_sheet(container)
    assert balance["opening"] == 500.0
    assert balance["used"] == 50.0
    assert balance["adjustment"] == -20.0
    assert balance["expected_closing"] == 430.0
    assert balance["physical_closing"] == 430.0
    assert balance["variance"] == 0.0
