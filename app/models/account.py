from sqlalchemy import Column, String, Numeric, Integer, ForeignKey
from app.database import Base

class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, index=True)
    currency = Column(String(3), nullable=False)
    balance = Column(Numeric(precision=18, scale=4), default=0.0, nullable=False)
    type = Column(String(50), nullable=False)  # "customer" or "external"
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # Links to User