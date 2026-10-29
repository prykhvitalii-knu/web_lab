import os
import shutil
from typing import List, Optional
from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File, Query
from sqlalchemy.orm import Session
from . import models, database

models.Base.metadata.create_all(bind=database.engine)

app = FastAPI(title="Akatosh API - Beer Recipe Book", version="1.0.0")

# Перевірка роботи API
@app.get("/")
def root():
    return {"status": "ok", "message": "Welcome to Akatosh API"}

# C1 + C5: Створення рецепта з можливістю завантаження файлу (зображення/PDF)
@app.post("/recipes/", status_code=status.HTTP_201_CREATED)
def create_recipe(
    title: str,
    style: str,
    abv: float,
    ibu: int,
    description: str = "",
    file: Optional[UploadFile] = File(None),
    db: Session = Depends(database.get_db)
):
    file_path = None
    if file:
        os.makedirs("uploads", exist_ok=True)
        file_path = f"uploads/{file.filename}"
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

    recipe = models.Recipe(
        title=title, style=style, abv=abv, ibu=ibu,
        description=description, file_path=file_path
    )
    db.add(recipe)
    db.commit()
    db.refresh(recipe)
    return recipe

# B1: Pagination API (skip, limit, next_link)
@app.get("/recipes/")
def list_recipes(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(database.get_db)
):
    recipes = db.query(models.Recipe).offset(skip).limit(limit).all()
    total = db.query(models.Recipe).count()
    
    next_skip = skip + limit
    next_link = f"/recipes/?skip={next_skip}&limit={limit}" if next_skip < total else None

    return {
        "items": recipes,
        "total": total,
        "skip": skip,
        "limit": limit,
        "next_link": next_link
    }
@app.get("/health", status_code=status.HTTP_200_OK)
def health_check():
    return {"status": "healthy", "app": "akatosh"}