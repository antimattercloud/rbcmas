from __future__ import annotations

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.common import TimestampMixin


class Supplier(Base, TimestampMixin):
    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    contact_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    email: Mapped[str | None] = mapped_column(String(150), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class Chemical(Base, TimestampMixin):
    __tablename__ = "chemicals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chemical_code: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    cas_number: Mapped[str | None] = mapped_column(String(30), index=True, nullable=True)
    formula: Mapped[str | None] = mapped_column(String(100), nullable=True)
    molecular_weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    grade: Mapped[str | None] = mapped_column(String(100), nullable=True)
    concentration: Mapped[str | None] = mapped_column(String(100), nullable=True)
    manufacturer: Mapped[str | None] = mapped_column(String(150), nullable=True)
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"), nullable=True)
    catalog_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    category: Mapped[str | None] = mapped_column(String(100), index=True, nullable=True)
    storage_requirements: Mapped[str | None] = mapped_column(String(255), nullable=True)
    temperature_requirements: Mapped[str | None] = mapped_column(String(100), nullable=True)
    physical_state: Mapped[str | None] = mapped_column(String(30), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    unit: Mapped[str] = mapped_column(String(20), default="mL", nullable=False)
    min_stock: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    reorder_level: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    target_stock: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    safety_stock: Mapped[float] = mapped_column(Float, default=0, nullable=False)

    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    supplier = relationship("Supplier")
    aliases = relationship("ChemicalAlias", back_populates="chemical", cascade="all, delete-orphan")
    containers = relationship("Container", back_populates="chemical")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Chemical {self.chemical_code} {self.name}>"


class ChemicalAlias(Base, TimestampMixin):
    __tablename__ = "chemical_aliases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chemical_id: Mapped[int] = mapped_column(ForeignKey("chemicals.id"), nullable=False, index=True)
    alias: Mapped[str] = mapped_column(String(200), index=True, nullable=False)

    chemical = relationship("Chemical", back_populates="aliases")


class Project(Base, TimestampMixin):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    laboratory_id: Mapped[int | None] = mapped_column(ForeignKey("laboratories.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    laboratory = relationship("Laboratory")
    experiments = relationship("Experiment", back_populates="project", cascade="all, delete-orphan")


class Experiment(Base, TimestampMixin):
    __tablename__ = "experiments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    project = relationship("Project", back_populates="experiments")
