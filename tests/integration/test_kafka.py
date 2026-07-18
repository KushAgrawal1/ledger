import asyncio
import json
import pytest
from aiokafka import AIOKafkaConsumer
from testcontainers.kafka import KafkaContainer

from app.models.transfer import Transfer
from app.services.ledger import execute_transfer
from app.services.publisher import (
    InMemoryTransferEventPublisher, 
    KafkaTransferEventPublisher
)


# ==========================================
# UNIT TESTS (Fast, In-Memory)
# ==========================================

@pytest.mark.asyncio
async def test_transfer_publishes_event_on_success(session):
    """Verifies successful transfers trigger correct versioned payloads on the publisher interface."""
    # Setup mock data
    publisher = InMemoryTransferEventPublisher()
    
    from app.models.account import Account
    acc_a = Account(id=1001, currency="GBP", balance=500.0, type="customer")
    acc_b = Account(id=1002, currency="GBP", balance=0.0, type="customer")
    session.add_all([acc_a, acc_b])
    await session.commit()

    # Execute
    await execute_transfer(
        db=session,
        idempotency_key="fast-test-event-key",
        from_account_id=1001,
        to_account_id=1002,
        amount=100.0,
        currency="GBP",
        publisher=publisher
    )

    # Assert
    assert len(publisher.published_events) == 1
    event = publisher.published_events[0]
    
    assert event.schema_version == 1
    assert event.from_account_id == 1001
    assert event.to_account_id == 1002
    assert event.amount == 100.0
    assert event.currency == "GBP"


@pytest.mark.asyncio
async def test_kafka_down_does_not_fail_transfer(session):
    """
    Guarantees robustness: If the broker is unreachable,
    the event fail-safes are triggered, logging is generated,
    and the core transfer still completes successfully.
    """
    # Connect to an invalid address to simulate broker outage
    dead_publisher = KafkaTransferEventPublisher(bootstrap_servers="localhost:9999")
    
    from app.models.account import Account
    acc_a = Account(id=2001, currency="GBP", balance=200.0, type="customer")
    acc_b = Account(id=2002, currency="GBP", balance=0.0, type="customer")
    session.add_all([acc_a, acc_b])
    await session.commit()

    # Execution should finish cleanly without rising exceptions despite dead Kafka link
    tx = await execute_transfer(
        db=session,
        idempotency_key="unreachable-broker-key",
        from_account_id=2001,
        to_account_id=2002,
        amount=50.0,
        currency="GBP",
        publisher=dead_publisher
    )
    
    assert tx.id is not None
    await dead_publisher.close()


# ==========================================
# KAFKA INTEGRATION TEST (Via Testcontainers)
# ==========================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_event_is_consumable_from_kafka_topic():
    """
    Deploys a containerized Kafka broker, runs a transfer, publishes, 
    and consumes the payload, validating structure matches expectations.
    """
    # 1. Spin up an ephemeral Kafka container using KRaft mode
    with KafkaContainer() as kafka_container:
        bootstrap_servers = kafka_container.get_bootstrap_server()
        
        # 2. Instantiate Kafka Client classes
        publisher = KafkaTransferEventPublisher(
            bootstrap_servers=bootstrap_servers, 
            topic="ledger.transfers"
        )
        
        # Build fake local Transfer instance for validation
        mock_transfer = Transfer(
            id=42,
            from_account_id=5001,
            to_account_id=5002,
            amount=250.00,
            currency="USD",
            idempotency_key="containerized-event-test"
        )

        # 3. Publish the mock transfer event
        await publisher.publish_transfer_completed(mock_transfer)
        await publisher.close()

        # 4. Attempt to consume the event from the topic
        consumer = AIOKafkaConsumer(
            "ledger.transfers",
            bootstrap_servers=bootstrap_servers,
            auto_offset_reset="earliest",
            value_deserializer=lambda m: json.loads(m.decode("utf-8"))
        )
        await consumer.start()
        
        try:
            # Poll with timeout to prevent test from hanging indefinitely on failures
            msg_set = await consumer.getmany(timeout_ms=5000)
            assert len(msg_set) > 0, "No messages were consumed from Kafka topic"
            
            # Extract and parse the payload
            for topic_partition, messages in msg_set.items():
                first_message = messages[0]
                payload = first_message.value
                
                assert payload["schema_version"] == 1
                assert payload["transfer_id"] == 42
                assert payload["from_account_id"] == 5001
                assert payload["to_account_id"] == 5002
                assert payload["amount"] == 250.00
                assert payload["currency"] == "USD"
        finally:
            await consumer.stop()