import pytest

from app.services.inventory_service import InsufficientQuantityError
from app.services.transfer_service import complete_transfer, create_transfer


def test_whole_container_transfer_moves_the_same_container(db, base_fixtures):
    container = base_fixtures["container"]
    manager = base_fixtures["manager"]
    researcher = base_fixtures["researcher"]
    lab_b = base_fixtures["lab_b"]

    transfer = create_transfer(
        db, container=container, quantity=500.0, destination_laboratory_id=lab_b.id,
        destination_location_id=None, sender=manager,
    )
    db.commit()
    assert transfer.status == "PENDING"

    complete_transfer(db, transfer=transfer, receiver=researcher)
    db.commit()

    assert transfer.status == "COMPLETED"
    assert transfer.destination_container_id == container.id  # same container, just moved
    assert container.laboratory_id == lab_b.id
    assert container.expected_quantity == 500.0  # net zero: out then in on the same container


def test_partial_transfer_splits_into_a_new_container(db, base_fixtures):
    container = base_fixtures["container"]
    manager = base_fixtures["manager"]
    researcher = base_fixtures["researcher"]
    lab_b = base_fixtures["lab_b"]
    source_lab_id = container.laboratory_id

    transfer = create_transfer(
        db, container=container, quantity=200.0, destination_laboratory_id=lab_b.id,
        destination_location_id=None, sender=manager,
    )
    db.commit()
    complete_transfer(db, transfer=transfer, receiver=researcher)
    db.commit()

    assert container.laboratory_id == source_lab_id  # source container stays put
    assert container.expected_quantity == 300.0  # 500 - 200

    assert transfer.destination_container_id != container.id
    new_container = transfer.destination_container
    assert new_container.laboratory_id == lab_b.id
    assert new_container.expected_quantity == 200.0
    assert new_container.chemical_id == container.chemical_id


def test_cannot_transfer_more_than_available(db, base_fixtures):
    container = base_fixtures["container"]
    manager = base_fixtures["manager"]
    lab_b = base_fixtures["lab_b"]

    with pytest.raises(InsufficientQuantityError):
        create_transfer(
            db, container=container, quantity=999999, destination_laboratory_id=lab_b.id,
            destination_location_id=None, sender=manager,
        )


def test_cannot_transfer_to_same_laboratory(db, base_fixtures):
    container = base_fixtures["container"]
    manager = base_fixtures["manager"]

    with pytest.raises(ValueError):
        create_transfer(
            db, container=container, quantity=10, destination_laboratory_id=container.laboratory_id,
            destination_location_id=None, sender=manager,
        )
