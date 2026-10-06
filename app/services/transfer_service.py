from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.models.common import ContainerStatus, TransactionType, TransferStatus, utcnow
from app.models.container import Container
from app.models.transfer import TransferRecord
from app.models.user import User
from app.services.audit_service import log_action
from app.services.codes import assign_code
from app.services.inventory_service import (
    EPSILON,
    InsufficientQuantityError,
    recompute_container_status,
    record_transaction,
)


def create_transfer(
    db: Session,
    *,
    container: Container,
    quantity: float,
    destination_laboratory_id: int,
    destination_location_id: int | None,
    sender: User,
    reason: str | None = None,
) -> TransferRecord:
    if quantity <= 0:
        raise ValueError("Transfer quantity must be greater than zero.")
    if quantity > container.expected_quantity:
        raise InsufficientQuantityError(
            f"Cannot transfer {quantity:g} {container.unit}: only "
            f"{container.expected_quantity:g} available in {container.container_code}."
        )
    if destination_laboratory_id == container.laboratory_id:
        raise ValueError("Source and destination laboratory must be different.")

    transfer = TransferRecord(
        transfer_code="",
        container_id=container.id,
        quantity=quantity,
        unit=container.unit,
        source_laboratory_id=container.laboratory_id,
        destination_laboratory_id=destination_laboratory_id,
        destination_location_id=destination_location_id,
        sender_id=sender.id,
        reason=reason,
        status=TransferStatus.PENDING.value,
    )
    db.add(transfer)
    assign_code(db, transfer, "transfer_code", "TRF-")

    log_action(
        db,
        user=sender,
        action="TRANSFER_REQUESTED",
        entity_type="transfer",
        entity_id=transfer.id,
        description=(
            f"Transfer {transfer.transfer_code} requested: {quantity:g} {container.unit} of "
            f"{container.container_code} to laboratory id={destination_laboratory_id}."
        ),
    )
    return transfer


def complete_transfer(
    db: Session,
    *,
    transfer: TransferRecord,
    receiver: User,
) -> TransferRecord:
    """Completes a pending transfer. If the transferred quantity equals the
    whole of the source container's current stock, the container itself
    moves laboratories. Otherwise the quantity is split: the source
    container is decremented and a new container is created at the
    destination, so a physical container is never in two places at once."""
    if transfer.status != TransferStatus.PENDING.value:
        raise ValueError("Only a pending transfer can be completed.")

    container = transfer.container
    if transfer.quantity > container.expected_quantity + EPSILON:
        raise InsufficientQuantityError(
            f"Only {container.expected_quantity:g} {container.unit} now available in "
            f"{container.container_code}; cannot complete a transfer of {transfer.quantity:g}."
        )

    is_full_transfer = abs(container.expected_quantity - transfer.quantity) < EPSILON

    out_txn = record_transaction(
        db,
        container=container,
        transaction_type=TransactionType.TRANSFER_OUT,
        quantity_delta=-transfer.quantity,
        user=receiver,
        reference_type="transfer",
        reference_id=transfer.id,
        notes=f"Transfer {transfer.transfer_code} to laboratory id={transfer.destination_laboratory_id}",
    )

    if is_full_transfer:
        container.laboratory_id = transfer.destination_laboratory_id
        if transfer.destination_location_id:
            container.location_id = transfer.destination_location_id
        container.responsible_user_id = receiver.id
        db.flush()

        in_txn = record_transaction(
            db,
            container=container,
            transaction_type=TransactionType.TRANSFER_IN,
            quantity_delta=transfer.quantity,
            user=receiver,
            reference_type="transfer",
            reference_id=transfer.id,
            notes=f"Transfer {transfer.transfer_code} received from laboratory id={transfer.source_laboratory_id}",
        )
        destination_container = container
    else:
        destination_container = Container(
            container_code="",
            chemical_id=container.chemical_id,
            batch_lot=container.batch_lot,
            container_size=transfer.quantity,
            unit=container.unit,
            initial_quantity=0.0,
            expected_quantity=0.0,
            date_received=date.today(),
            expiry_date=container.expiry_date,
            location_id=transfer.destination_location_id,
            laboratory_id=transfer.destination_laboratory_id,
            responsible_user_id=receiver.id,
            status=ContainerStatus.AVAILABLE.value,
            notes=f"Split from {container.container_code} via transfer {transfer.transfer_code}",
            is_demo=container.is_demo,
        )
        db.add(destination_container)
        assign_code(db, destination_container, "container_code", "CHEM-")

        in_txn = record_transaction(
            db,
            container=destination_container,
            transaction_type=TransactionType.TRANSFER_IN,
            quantity_delta=transfer.quantity,
            user=receiver,
            reference_type="transfer",
            reference_id=transfer.id,
            notes=f"Transfer {transfer.transfer_code} received from laboratory id={transfer.source_laboratory_id}",
        )
        recompute_container_status(db, container)

    transfer.transaction_out_id = out_txn.id
    transfer.transaction_in_id = in_txn.id
    transfer.destination_container_id = destination_container.id
    transfer.receiver_id = receiver.id
    transfer.status = TransferStatus.COMPLETED.value
    transfer.completed_at = utcnow()
    db.flush()

    log_action(
        db,
        user=receiver,
        action="TRANSFER_COMPLETED",
        entity_type="transfer",
        entity_id=transfer.id,
        description=(
            f"Transfer {transfer.transfer_code} completed: {transfer.quantity:g} {transfer.unit} now in "
            f"{destination_container.container_code} at laboratory id={transfer.destination_laboratory_id}."
        ),
    )
    return transfer


def reject_transfer(db: Session, *, transfer: TransferRecord, user: User, reason: str | None = None) -> TransferRecord:
    if transfer.status != TransferStatus.PENDING.value:
        raise ValueError("Only a pending transfer can be rejected.")
    transfer.status = TransferStatus.REJECTED.value
    transfer.reason = f"{transfer.reason or ''}\nRejected: {reason or 'no reason given'}".strip()
    db.flush()
    log_action(
        db,
        user=user,
        action="TRANSFER_REJECTED",
        entity_type="transfer",
        entity_id=transfer.id,
        description=f"Transfer {transfer.transfer_code} rejected.",
    )
    return transfer
