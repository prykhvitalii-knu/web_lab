import uuid
from sqlalchemy import Boolean, Column, Integer, String, Float, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from .database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    tenant_id = Column(String, default=lambda: str(uuid.uuid4()), index=True)

    recipes = relationship("Recipe", back_populates="owner")


class Recipe(Base):
    __tablename__ = "recipes"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True, nullable=False)
    style = Column(String, nullable=False)
    abv = Column(Float)
    ibu = Column(Integer)
    description = Column(Text)
    file_path = Column(String, nullable=True)
    owner_id = Column(Integer, ForeignKey("users.id"))

    owner = relationship("User", back_populates="recipes")
    ingredients = relationship("Ingredient", back_populates="recipe", cascade="all, delete-orphan")


class Ingredient(Base):
    __tablename__ = "ingredients"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    amount_grams = Column(Float, nullable=False)
    ingredient_type = Column(String)
    recipe_id = Column(Integer, ForeignKey("recipes.id"))

    recipe = relationship("Recipe", back_populates="ingredients")


class TenantFeatureFlag(Base):
    __tablename__ = "tenant_feature_flags"
    __table_args__ = (UniqueConstraint("tenant_id", "name"),)

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False)
    enabled = Column(Boolean, nullable=False, default=False)