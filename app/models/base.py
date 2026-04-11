from abc import abstractmethod
from datetime import datetime
import hashlib
from typing import Any, Dict, List

from sqlalchemy import JSON, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import db

# Shared declarative base from the async singleton
Base = db.base


def get_delimiter() -> str:
    return "|"


def calculate_sha256_hash_first_ten(input_string: str) -> str:
    sha256_hash = hashlib.sha256()
    sha256_hash.update(input_string.encode("utf-8"))
    hashed_string: str = sha256_hash.hexdigest()
    return hashed_string[0:10]


class BaseModel(Base):
    __abstract__ = True

    created_at: Mapped[datetime] = mapped_column(
        "CREATED_AT", DateTime, nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        "UPDATED_AT", DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    meta_data: Mapped[Dict[Any, Any]] = mapped_column(
        "METADATA", JSON, nullable=False, default=dict
    )

    @abstractmethod
    def token(self) -> str:
        pass

    @abstractmethod
    def get_identifiers(self) -> List[Any]:
        pass

    def compute_and_get_id(self) -> str:
        identifier_string: str = ""
        for identifier in self.get_identifiers():
            identifier_string += str(identifier) + get_delimiter()
        return self.token() + "_" + calculate_sha256_hash_first_ten(identifier_string)
