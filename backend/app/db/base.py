from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base déclarative. Le schéma est piloté par les migrations SQL (sql/)."""
