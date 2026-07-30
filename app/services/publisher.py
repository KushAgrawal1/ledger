import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Protocol

from aiokafka import AIOKafkaProducer

from app.api.schemas import TransferCompletedEvent
from app.models.transfer import Transfer


def _json_serialise(obj):
    """JSON encoder that handles Decimal and datetime — both appear in transfer events."""
    from datetime import datetime
    from decimal import Decimal
    if isinstance(obj, Decimal):
        return str(obj)       # "100.0000" — preserves precision
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Cannot serialise type {type(obj).__name__}")



logger = logging.getLogger(__name__)

class TransferEventPublisher(Protocol):
    """Protocol establishing a decoupling layer for outbound events."""
    async def publish_transfer_completed(self, transfer: Transfer) -> None:
        ...

# ==========================================
# PRODUCTION-READY AIOKAFKA PUBLISHER
# ==========================================
class KafkaTransferEventPublisher:
    def __init__(self, bootstrap_servers: str, topic: str = "ledger.transfers"):
        self.bootstrap_servers = bootstrap_servers
        self.topic = topic
        self._producer = None

    async def _get_producer(self) -> AIOKafkaProducer:
        if self._producer is None:
            self._producer = AIOKafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                value_serializer=lambda v: json.dumps(v, default=_json_serialise).encode("utf-8")
            )
            await self._producer.start()
        return self._producer

    async def publish_transfer_completed(self, transfer: Transfer) -> None:
        """Publishes transfer.completed events. Kafka failures must NOT fail the transfer."""
        event = TransferCompletedEvent(
            event_id=str(uuid.uuid4()),
            transfer_id=transfer.id,
            from_account_id=transfer.from_account_id,
            to_account_id=transfer.to_account_id,
            amount=transfer.amount,
            currency=transfer.currency,
            timestamp=datetime.now(UTC)
        )
        
        try:
            producer = await self._get_producer()
            # Send the payload to the Kafka broker asynchronously
            await producer.send_and_wait(self.topic, event.model_dump())
            logger.info(f"Successfully published transfer.completed event for transfer {transfer.id}")
        except Exception as e:
            # Fallback Guard: Ledger commits are the source of truth. Log warning, but never crash execution.
            logger.error(
                f"Kafka failure! Event delivery failed for Transfer ID {transfer.id}. "
                f"Error: {str(e)}"
            )

    async def close(self) -> None:
        if self._producer is not None:
            await self._producer.stop()


# ==========================================
# IN-MEMORY TESTING MOCK
# ==========================================
class InMemoryTransferEventPublisher:
    def __init__(self):
        self.published_events = []

    async def publish_transfer_completed(self, transfer: Transfer) -> None:
        event = TransferCompletedEvent(
            event_id=str(uuid.uuid4()),
            transfer_id=transfer.id,
            from_account_id=transfer.from_account_id,
            to_account_id=transfer.to_account_id,
            amount=transfer.amount,
            currency=transfer.currency,
            timestamp=datetime.now(UTC)
        )
        self.published_events.append(event)