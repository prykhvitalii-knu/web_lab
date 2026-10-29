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
    owner_id: int
) -> models.Recipe:
    recipe = models.Recipe(
        title=title, style=style, abv=abv, ibu=ibu,
        description=description, file_path=file_path,
        owner_id=owner_id
    )
    db.add(recipe)
    db.commit()
    db.refresh(recipe)
    return recipe

def get_recipes(db: Session, skip: int = 0, limit: int = 10) -> List[models.Recipe]:
    return db.query(models.Recipe).offset(skip).limit(limit).all()

def get_recipes_count(db: Session) -> int:
    return db.query(models.Recipe).count()