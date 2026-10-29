import os
import json
import shutil
from typing import Optional
import redis
from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File, Query, Form, Header
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from . import models, schemas, database, auth, crud
from .worker import process_recipe_file_task, send_telegram_notification_task

models.Base.metadata.create_all(bind=database.engine)

app = FastAPI(title="Akatosh API - Beer Recipe Book", version="1.0.0")

# Redis
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)

def get_tenant_id(x_tenant_id: Optional[str] = Header(default="default")):
    return x_tenant_id

@app.get("/health", status_code=status.HTTP_200_OK)
def health_check():
    return {"status": "healthy", "app": "akatosh"}

@app.get("/")
def root():
    return {"status": "ok", "message": "Welcome to Akatosh API"}


@app.post("/register", response_model=schemas.UserResponse, status_code=status.HTTP_201_CREATED)
def register(user_data: schemas.UserCreate, db: Session = Depends(database.get_db)):
    if crud.get_user_by_email(db, user_data.email):
        raise HTTPException(status_code=400, detail="Email already registered")
    return crud.create_user(db, user_data)

@app.post("/login", response_model=schemas.Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(database.get_db)):
    user = crud.get_user_by_email(db, form_data.username)
    if not user or not auth.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect email or password")
    access_token = auth.create_access_token(data={"sub": user.email})
    return {"access_token": access_token, "token_type": "bearer"}


FEATURE_FLAGS = {"enable_pdf_export": True, "enable_ai_suggestions": False, "premium_analytics": True}

@app.get("/features/")
def get_feature_flags(current_user: models.User = Depends(auth.get_current_user)):
    return {"tenant_id": current_user.tenant_id, "flags": FEATURE_FLAGS}

@app.get("/tenant/info")
def get_tenant_info(tenant_id: str = Depends(get_tenant_id), current_user: models.User = Depends(auth.get_current_user)):
    return {"user_email": current_user.email, "tenant_id": tenant_id, "message": f"Data isolated for tenant: {tenant_id}"}


@app.post("/recipes/", response_model=schemas.RecipeResponse, status_code=status.HTTP_201_CREATED)
def create_recipe(
    title: str = Form(...),
    style: str = Form(...),
    abv: float = Form(...),
    ibu: int = Form(...),
    description: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    tenant_id: str = Depends(get_tenant_id),
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db)
):
    file_path = None
    if file:
        os.makedirs("uploads", exist_ok=True)
        file_path = f"uploads/{file.filename}"
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

    recipe = crud.create_recipe(db, title, style, abv, ibu, description, file_path, current_user.id)

    if file_path:
        process_recipe_file_task.delay(file_path, recipe.title)
    send_telegram_notification_task.delay(recipe.title, recipe.style, recipe.abv)

    try:
        for key in redis_client.scan_iter("recipes_*"):
            redis_client.delete(key)
    except Exception as e:
        print(f"Redis cache invalidation error: {e}")

    return recipe

@app.get("/recipes/", response_model=schemas.PaginatedRecipesResponse)
def list_recipes(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(database.get_db)
):
    cache_key = f"recipes_tenant_{tenant_id}_skip_{skip}_limit_{limit}"
    try:
        cached = redis_client.get(cache_key)
        if cached:
            return json.loads(cached)
    except Exception as e:
        print(f"Redis cache read error: {e}")

    recipes = crud.get_recipes(db, skip=skip, limit=limit)
    total = crud.get_recipes_count(db)
    next_skip = skip + limit
    next_link = f"/recipes/?skip={next_skip}&limit={limit}" if next_skip < total else None

    response_data = {
        "items": [schemas.RecipeResponse.model_validate(r).model_dump() for r in recipes],
        "total": total,
        "skip": skip,
        "limit": limit,
        "next_link": next_link
    }

    try:
        redis_client.setex(cache_key, 60, json.dumps(response_data))
    except Exception as e:
        print(f"Redis cache write error: {e}")

    return response_data