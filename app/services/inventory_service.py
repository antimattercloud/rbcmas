from __future__ import annotations

from datetime import date, datetime

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.common import ContainerStatus, TransactionType, utcnow
from app.models.container import Container
from app.models.transaction import InventoryTransaction
from app.models.transfer import InventoryAdjustment, PhysicalCount
from app.models.user import User
from app.services.audit_service import log_action
from app.services.settings_service import get_setting

settings = get_settings()

EPSILON = 1e-9
LOW_STOCK_FRACTION = 0.10


class InsufficientQuantityError(Exception):
    pass


class ReasonRequiredError(Exception):
    pass


def record_transaction(
    db: Session,
    *,
    container: Container,
    transaction_type: TransactionType,
    quantity_delta: float,
    user: User,
    unit: str | None = None,
    purpose: str | None = None,
    project_id: int | None = None,
    experiment_id: int | None = None,
    reference_type: str | None = None,
    reference_id: int | None = None,
    notes: str | None = None,
    occurred_at: datetime | None = None,
    allow_negative: bool = False,
) -> InventoryTransaction:
    before = container.expected_quantity
    after = before + quantity_delta
    if after < -EPSILON and not allow_negative:
        raise InsufficientQuantityError(
            f"Only {before:g} {container.unit} available in {container.container_code}, "
            f"cannot record a change of {quantity_delta:g}."
        )
    if abs(after) < EPSILON:
        after = 0.0

    txn = InventoryTransaction(
        container_id=container.id,
        transaction_type=transaction_type.value,
        quantity_delta=quantity_delta,
        unit=unit or container.unit,
        expected_quantity_before=before,
        expected_quantity_after=after,
        user_id=user.id,
        purpose=purpose,
        project_id=project_id,
        experiment_id=experiment_id,
        reference_type=reference_type,
        reference_id=reference_id,
        notes=notes,
        occurred_at=occurred_at or utcnow(),
    )
    db.add(txn)
    container.expected_quantity = after
    db.flush()

    recompute_container_status(db, container)
    db.flush()
    return txn


def recompute_container_status(db: Session, container: Container, force: bool = False) -> str:
    """Derives container.status from its current quantity/expiry. Manual
    states (ARCHIVED, UNDER_REVIEW) are preserved unless force=True."""
    if not force and container.status in (
        ContainerStatus.ARCHIVED.value,
        ContainerStatus.UNDER_REVIEW.value,
    ):
        return container.status

    today = date.today()
    new_status = ContainerStatus.AVAILABLE.value
    expiry_warning_days_3 = get_setting(db, "expiry_warning_days_3", settings.expiry_warning_days_3)

    if container.expected_quantity <= EPSILON:
        new_status = ContainerStatus.EMPTY.value
    elif container.expiry_date and container.expiry_date < today:
        new_status = ContainerStatus.EXPIRED.value
    elif container.expiry_date and (container.expiry_date - today).days <= expiry_warning_days_3:
        new_status = ContainerStatus.EXPIRING_SOON.value
    elif container.container_size > 0 and (
        container.expected_quantity / container.container_size
    ) <= LOW_STOCK_FRACTION:
        new_status = ContainerStatus.LOW_STOCK.value

    container.status = new_status
    return new_status


def receive_container(
    db: Session,
    *,
    container: Container,
    user: User,
    notes: str | None = None,
) -> InventoryTransaction:
    """Initial RECEIVE transaction establishing opening stock for a new container."""
    return record_transaction(
        db,
        container=container,
        transaction_type=TransactionType.RECEIVE,
        quantity_delta=container.initial_quantity,
        user=user,
        notes=notes or "Initial receipt",
    )


def record_usage(
    db: Session,
    *,
    container: Container,
    quantity_used: float,
    user: User,
    purpose: str | None = None,
    project_id: int | None = None,
    experiment_id: int | None = None,
    notes: str | None = None,
) -> InventoryTransaction:
    if quantity_used <= 0:
        raise ValueError("Quantity used must be greater than zero.")
    txn = record_transaction(
        db,
        container=container,
        transaction_type=TransactionType.USE,
        quantity_delta=-quantity_used,
        user=user,
        purpose=purpose,
        project_id=project_id,
        experiment_id=experiment_id,
        notes=notes,
    )
    log_action(
        db,
        user=user,
        action="USE",
        entity_type="container",
        entity_id=container.id,
        description=(
            f"Used {quantity_used:g} {container.unit} from {container.container_code}. "
            f"Expected: {txn.expected_quantity_before:g} -> {txn.expected_quantity_after:g}."
        ),
    )
    return txn


def record_physical_count(
    db: Session,
    *,
    container: Container,
    physical_quantity: float,
    user: User,
    reason: str | None = None,
    notes: str | None = None,
) -> tuple[PhysicalCount, InventoryTransaction, InventoryAdjustment | None]:
    """Records a physical verification as a zero-delta PHYSICAL_COUNT ledger
    checkpoint, and - if the variance exceeds tolerance - opens a pending
    InventoryAdjustment that requires a reason and (for larger variances)
    manager/admin approval before it touches expected_quantity."""
    if physical_quantity < 0:
        raise ValueError("Physical quantity cannot be negative.")

    expected = container.expected_quantity
    variance = physical_quantity - expected
    variance_percent = (variance / expected * 100) if expected > EPSILON else (100.0 if variance else 0.0)
    tolerance = get_setting(db, "variance_tolerance_percent", settings.variance_tolerance_percent)
    tolerance_exceeded = abs(variance_percent) > tolerance

    if tolerance_exceeded and not reason:
        raise ReasonRequiredError(
            f"Variance of {variance:+g} {container.unit} ({variance_percent:+.2f}%) exceeds the "
            f"{tolerance:g}% tolerance. A reason is required before this can be recorded."
        )

    checkpoint_txn = record_transaction(
        db,
        container=container,
        transaction_type=TransactionType.PHYSICAL_COUNT,
        quantity_delta=0.0,
        user=user,
        notes=f"Physical count: {physical_quantity:g} {container.unit}",
    )

    count = PhysicalCount(
        container_id=container.id,
        transaction_id=checkpoint_txn.id,
        expected_quantity=expected,
        physical_quantity=physical_quantity,
        variance=variance,
        variance_percent=variance_percent,
        counted_by_id=user.id,
        reason=reason,
        notes=notes,
        requires_review=tolerance_exceeded,
    )
    db.add(count)
    container.last_physical_quantity = physical_quantity
    container.last_physical_count_at = date.today()
    db.flush()

    adjustment = None
    if tolerance_exceeded:
        adjustment = InventoryAdjustment(
            container_id=container.id,
            physical_count_id=count.id,
            previous_expected_quantity=expected,
            physical_quantity=physical_quantity,
            difference=variance,
            reason=reason or "Other",
            reason_notes=notes,
            requested_by_id=user.id,
            approval_status="PENDING",
        )
        db.add(adjustment)
        db.flush()

    log_action(
        db,
        user=user,
        action="PHYSICAL_COUNT",
        entity_type="container",
        entity_id=container.id,
        description=(
            f"Physical count on {container.container_code}: expected {expected:g}, "
            f"physical {physical_quantity:g}, variance {variance:+g} ({variance_percent:+.2f}%)."
        ),
    )

    recompute_container_status(db, container)
    db.flush()
    return count, checkpoint_txn, adjustment


def decide_adjustment(
    db: Session,
    *,
    adjustment: InventoryAdjustment,
    approve: bool,
    approver: User,
) -> InventoryAdjustment:
    if adjustment.approval_status != "PENDING":
        raise ValueError("This adjustment has already been decided.")

    adjustment.approved_by_id = approver.id
    adjustment.decided_at = utcnow()

    if approve:
        container = adjustment.container
        txn = record_transaction(
            db,
            container=container,
            transaction_type=TransactionType.ADJUSTMENT,
            quantity_delta=adjustment.difference,
            user=approver,
            reference_type="inventory_adjustment",
            reference_id=adjustment.id,
            notes=f"Adjustment approved: {adjustment.reason}",
        )
        adjustment.transaction_id = txn.id
        adjustment.approval_status = "APPROVED"
        log_action(
            db,
            user=approver,
            action="ADJUSTMENT_APPROVED",
            entity_type="container",
            entity_id=container.id,
            description=(
                f"Adjustment approved on {container.container_code}: "
                f"{adjustment.previous_expected_quantity:g} -> {adjustment.physical_quantity:g} "
                f"({adjustment.reason})."
            ),
        )
    else:
        adjustment.approval_status = "REJECTED"
        log_action(
            db,
            user=approver,
            action="ADJUSTMENT_REJECTED",
            entity_type="container",
            entity_id=adjustment.container_id,
            description=f"Adjustment rejected on container id={adjustment.container_id} ({adjustment.reason}).",
        )

    db.flush()
    return adjustment


def calculate_balance_sheet(container: Container) -> dict:
    """Opening + Received + TransferIn - Used - TransferOut + Adjustment = Expected closing,
    compared against the last physical closing count."""
    totals = {
        "opening": container.initial_quantity,
        "received": 0.0,
        "transfer_in": 0.0,
        "used": 0.0,
        "transfer_out": 0.0,
        "adjustment": 0.0,
        "returned": 0.0,
    }
    for txn in container.transactions:
        if txn.transaction_type == TransactionType.RECEIVE.value:
            continue  # captured as opening/initial_quantity already
        elif txn.transaction_type == TransactionType.TRANSFER_IN.value:
            totals["transfer_in"] += txn.quantity_delta
        elif txn.transaction_type == TransactionType.USE.value:
            totals["used"] += -txn.quantity_delta
        elif txn.transaction_type == TransactionType.TRANSFER_OUT.value:
            totals["transfer_out"] += -txn.quantity_delta
        elif txn.transaction_type == TransactionType.ADJUSTMENT.value:
            totals["adjustment"] += txn.quantity_delta
        elif txn.transaction_type == TransactionType.RETURN.value:
            totals["returned"] += txn.quantity_delta

    expected_closing = (
        totals["opening"]
        + totals["received"]
        + totals["transfer_in"]
        + totals["returned"]
        - totals["used"]
        - totals["transfer_out"]
        + totals["adjustment"]
    )
    physical_closing = container.last_physical_quantity
    variance = None
    variance_percent = None
    if physical_closing is not None:
        variance = physical_closing - expected_closing
        variance_percent = (variance / expected_closing * 100) if expected_closing > EPSILON else 0.0

    return {
        **totals,
        "expected_closing": expected_closing,
        "physical_closing": physical_closing,
        "variance": variance,
        "variance_percent": variance_percent,
    }
