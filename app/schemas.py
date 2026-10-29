from typing import List, Optional
from pydantic import BaseModel, EmailStr, ConfigDict

# --- AUTH & USER ---
class UserBase(BaseModel):
    email: EmailStr

class UserCreate(UserBase):
    password: str

class UserResponse(UserBase):
    id: int
    tenant_id: str

    model_config = ConfigDict(from_attributes=True)

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None

# --- INGREDIENT ---
class IngredientBase(BaseModel):
    name: str
    amount_grams: float
    ingredient_type: str

class IngredientResponse(IngredientBase):
    id: int
    recipe_id: int

    model_config = ConfigDict(from_attributes=True)

# --- RECIPE ---
class RecipeBase(BaseModel):
    title: str
    style: str
    abv: float
    ibu: int
    description: Optional[str] = None

class RecipeResponse(RecipeBase):
    id: int
    file_path: Optional[str] = None
    owner_id: int
    ingredients: List[IngredientResponse] = []

    model_config = ConfigDict(from_attributes=True)

class PaginatedRecipesResponse(BaseModel):
    items: List[RecipeResponse]
    total: int
    skip: int
    limit: int
    next_link: Optional[str] = None