from sqlalchemy import Column, Integer, String, Float, ForeignKey, Text
from sqlalchemy.orm import relationship
from .database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    tenant_id = Column(String, default="default")  # Для B5 (Tenant Isolation)

    recipes = relationship("Recipe", back_populates="owner")


class Recipe(Base):
    __tablename__ = "recipes"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True, nullable=False)
    style = Column(String, nullable=False)  # IPA, Stout, Lager...
    abv = Column(Float)  # Alcohol by volume
    ibu = Column(Integer)  # International Bitterness Units
    description = Column(Text)
    file_path = Column(String, nullable=True)
    owner_id = Column(Integer, ForeignKey("users.id"))

    owner = relationship("User", back_populates="recipes")
    ingredients = relationship("Ingredient", back_populates="recipe", cascade="all, delete-orphan")


class Ingredient(Base):
    __tablename__ = "ingredients"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)  # Наприклад: "Cascade Hop", "Pilsner Malt"
    amount_grams = Column(Float, nullable=False)
    ingredient_type = Column(String)  # Hop, Malt, Yeast, Additive
    recipe_id = Column(Integer, ForeignKey("recipes.id"))

    recipe = relationship("Recipe", back_populates="ingredients")