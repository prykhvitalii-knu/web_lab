import os
from typing import Optional, List
from sqlalchemy.orm import Session
from . import models, schemas, auth


def get_user_by_email(db: Session, email: str) -> Optional[models.User]:
    return db.query(models.User).filter(models.User.email == email).first()

def create_user(db: Session, user_data: schemas.UserCreate) -> models.User:
    hashed_pwd = auth.get_password_hash(user_data.password)
    new_user = models.User(email=user_data.email, hashed_password=hashed_pwd)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user


def create_recipe(
    db: Session,
    title: str,
    style: str,
    abv: float,
    ibu: int,
    description: Optional[str],
    file_path: Optional[str],
    owner_id: int,
    ingredients: Optional[List[schemas.IngredientCreate]] = None,
) -> models.Recipe:
    recipe = models.Recipe(
        title=title, style=style, abv=abv, ibu=ibu,
        description=description, file_path=file_path,
        owner_id=owner_id
    )
    recipe.ingredients = [
        models.Ingredient(**ingredient.model_dump())
        for ingredient in (ingredients or [])
    ]
    db.add(recipe)
    db.commit()
    db.refresh(recipe)
    return recipe

def get_recipes(
    db: Session, tenant_id: str, skip: int = 0, limit: int = 10
) -> List[models.Recipe]:
    return (
        db.query(models.Recipe)
        .join(models.User, models.Recipe.owner_id == models.User.id)
        .filter(models.User.tenant_id == tenant_id)
        .order_by(models.Recipe.id)
        .offset(skip)
        .limit(limit)
        .all()
    )

def get_recipes_count(db: Session, tenant_id: str) -> int:
    return (
        db.query(models.Recipe)
        .join(models.User, models.Recipe.owner_id == models.User.id)
        .filter(models.User.tenant_id == tenant_id)
        .count()
    )

def get_recipe(
    db: Session, recipe_id: int, tenant_id: str
) -> Optional[models.Recipe]:
    return (
        db.query(models.Recipe)
        .join(models.User, models.Recipe.owner_id == models.User.id)
        .filter(
            models.Recipe.id == recipe_id,
            models.User.tenant_id == tenant_id,
        )
        .first()
    )

def update_recipe(
    db: Session, recipe: models.Recipe, recipe_data: schemas.RecipeUpdate
) -> models.Recipe:
    updates = recipe_data.model_dump(exclude_unset=True)
    ingredients = updates.pop("ingredients", None)
    for field, value in updates.items():
        if value is None and field != "description":
            continue
        setattr(recipe, field, value)
    if ingredients is not None:
        recipe.ingredients = [
            models.Ingredient(**ingredient)
            for ingredient in ingredients
        ]
    db.commit()
    db.refresh(recipe)
    return recipe

def delete_recipe(db: Session, recipe: models.Recipe) -> None:
    db.delete(recipe)
    db.commit()

def get_feature_flags(db: Session, tenant_id: str) -> dict[str, bool]:
    defaults = {
        "enable_pdf_export": True,
        "enable_ai_suggestions": bool(os.getenv("GEMINI_API_KEY")),
        "premium_analytics": True,
    }
    configured = {
        flag.name: bool(flag.enabled)
        for flag in db.query(models.TenantFeatureFlag)
        .filter(models.TenantFeatureFlag.tenant_id == tenant_id)
        .all()
    }
    return {**defaults, **configured}

def set_feature_flag(
    db: Session, tenant_id: str, name: str, enabled: bool
) -> models.TenantFeatureFlag:
    feature = (
        db.query(models.TenantFeatureFlag)
        .filter_by(tenant_id=tenant_id, name=name)
        .first()
    )
    if feature is None:
        feature = models.TenantFeatureFlag(
            tenant_id=tenant_id, name=name, enabled=enabled
        )
        db.add(feature)
    else:
        feature.enabled = enabled
    db.commit()
    db.refresh(feature)
    return feature