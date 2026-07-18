from sqlalchemy import Column, ForeignKey, Integer, Numeric, String

from app.database import Base


class Transfer(Base):
    __tablename__ = "transfers"

    id = Column(Integer, primary_key=True, index=True)
    idempotency_key = Column(String(255), unique=True, nullable=False, index=True)
    from_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    to_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    amount = Column(Numeric(precision=18, scale=4), nullable=False)
    currency = Column(String(3), nullable=False)
    status = Column(String(50), default="completed", nullable=False)