import json
import logging

from aiokafka import AIOKafkaProducer

from app.core.config import settings

logger = logging.getLogger(__name__)
_producer: AIOKafkaProducer | None = None

async def get_producer() -> AIOKafkaProducer:
    global _producer
    if _producer is None:
        _producer = AIOKafkaProducer(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        )
        await _producer.start()
    return _producer

async def publish_transfer_event(transfer_id: str, amount: str, 
                                  from_account: str, to_account: str,
                                  currency: str) -> None:
    producer = await get_producer()
    event = {
        "event_type": "transfer.completed",
        "transfer_id": transfer_id,
        "amount": amount,
        "from_account": from_account,
        "to_account": to_account,
        "currency": currency,
    }
    await producer.send_and_wait("ledger.transfers", value=event)
    logger.info("Published transfer event", extra={"transfer_id": transfer_id})