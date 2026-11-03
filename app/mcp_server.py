import json
import os

from mcp.server.fastmcp import FastMCP

from . import crud, database, models, schemas


TENANT_ID = os.getenv("MCP_TENANT_ID")
if not TENANT_ID:
    raise RuntimeError("Set MCP_TENANT_ID before starting the MCP server")

mcp = FastMCP(
    "Akatosh Beer Recipes",
    instructions="Read and create beer recipes in the configured tenant.",
)


def _recipe_json(recipe: models.Recipe) -> str:
    return schemas.RecipeResponse.model_validate(recipe).model_dump_json()


@mcp.tool()
def list_recipes(skip: int = 0, limit: int = 20) -> str:
    """List recipes in the configured tenant."""
    if skip < 0 or limit < 1 or limit > 100:
        raise ValueError("skip must be non-negative and limit must be from 1 to 100")
    with database.SessionLocal() as db:
        recipes = crud.get_recipes(db, TENANT_ID, skip=skip, limit=limit)
        total = crud.get_recipes_count(db, TENANT_ID)
        return json.dumps(
            {
                "items": [
                    json.loads(_recipe_json(recipe)) for recipe in recipes
                ],
                "total": total,
                "skip": skip,
                "limit": limit,
            }
        )


@mcp.tool()
def get_recipe(recipe_id: int) -> str:
    """Read one recipe by ID, only if it belongs to the configured tenant."""
    with database.SessionLocal() as db:
        recipe = crud.get_recipe(db, recipe_id, TENANT_ID)
        if recipe is None:
            raise ValueError("Recipe not found")
        return _recipe_json(recipe)


@mcp.tool()
def list_recipe_ingredients(recipe_id: int) -> str:
    """List ingredients for a recipe in the configured tenant."""
    with database.SessionLocal() as db:
        recipe = crud.get_recipe(db, recipe_id, TENANT_ID)
        if recipe is None:
            raise ValueError("Recipe not found")
        return json.dumps(
            [
                schemas.IngredientResponse.model_validate(ingredient).model_dump()
                for ingredient in recipe.ingredients
            ]
        )


@mcp.tool()
def create_recipe(
    title: str,
    style: str,
    abv: float,
    ibu: int,
    description: str = "",
) -> str:
    """Create a recipe in the configured tenant."""
    with database.SessionLocal() as db:
        owner = (
            db.query(models.User)
            .filter(models.User.tenant_id == TENANT_ID)
            .order_by(models.User.id)
            .first()
        )
        if owner is None:
            raise ValueError("The configured tenant has no registered user")
        recipe = crud.create_recipe(
            db,
            title=title,
            style=style,
            abv=abv,
            ibu=ibu,
            description=description or None,
            file_path=None,
            owner_id=owner.id,
        )
        return _recipe_json(recipe)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
