from sqlalchemy import Column, ForeignKey, Integer, Numeric

from app.database import Base


class Entry(Base):
    __tablename__ = "entries"

    id = Column(Integer, primary_key=True, index=True)
    transfer_id = Column(Integer, ForeignKey("transfers.id"), nullable=False)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    amount = Column(Numeric(precision=18, scale=4), nullable=False)  # Negative for debits, positive for credits