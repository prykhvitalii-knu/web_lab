from typing import List, Optional
from pydantic import BaseModel, EmailStr, ConfigDict, Field

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

class IngredientBase(BaseModel):
    name: str
    amount_grams: float
    ingredient_type: str

class IngredientCreate(IngredientBase):
    pass

class IngredientResponse(IngredientBase):
    id: int
    recipe_id: int

    model_config = ConfigDict(from_attributes=True)

class RecipeBase(BaseModel):
    title: str
    style: str
    abv: float
    ibu: int
    description: Optional[str] = None

class RecipeCreate(RecipeBase):
    ingredients: List[IngredientCreate] = Field(default_factory=list)

class RecipeUpdate(BaseModel):
    title: Optional[str] = None
    style: Optional[str] = None
    abv: Optional[float] = None
    ibu: Optional[int] = None
    description: Optional[str] = None
    ingredients: Optional[List[IngredientCreate]] = None

class RecipeResponse(RecipeBase):
    id: int
    file_path: Optional[str] = None
    owner_id: int
    ingredients: List[IngredientResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)

class PaginatedRecipesResponse(BaseModel):
    items: List[RecipeResponse]
    total: int
    skip: int
    limit: int
    next_link: Optional[str] = None

class FeatureFlagUpdate(BaseModel):
    enabled: bool

class AssistantPrompt(BaseModel):
    prompt: str = Field(min_length=1, max_length=1000)