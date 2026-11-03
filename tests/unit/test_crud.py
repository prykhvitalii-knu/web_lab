from unittest.mock import Mock, patch

from app import crud, models, schemas


def test_create_user_hashes_password_and_persists_user():
    db = Mock()
    user_data = schemas.UserCreate(
        email="brewer@example.com",
        password="brewing-password",
    )

    with patch("app.crud.auth.get_password_hash", return_value="hashed-password"):
        user = crud.create_user(db, user_data)

    assert user.email == "brewer@example.com"
    assert user.hashed_password == "hashed-password"
    db.add.assert_called_once_with(user)
    db.commit.assert_called_once_with()
    db.refresh.assert_called_once_with(user)


def test_create_recipe_includes_ingredients_and_persists():
    db = Mock()
    ingredients = [
        schemas.IngredientCreate(
            name="Cascade",
            amount_grams=25,
            ingredient_type="Hop",
        )
    ]

    recipe = crud.create_recipe(
        db,
        title="Cascade Pale Ale",
        style="Pale Ale",
        abv=5.2,
        ibu=42,
        description="Citrus aroma",
        file_path=None,
        owner_id=7,
        ingredients=ingredients,
    )

    assert recipe.title == "Cascade Pale Ale"
    assert recipe.owner_id == 7
    assert len(recipe.ingredients) == 1
    assert recipe.ingredients[0].name == "Cascade"
    assert recipe.ingredients[0].amount_grams == 25
    db.add.assert_called_once_with(recipe)
    db.commit.assert_called_once_with()
    db.refresh.assert_called_once_with(recipe)


def test_update_recipe_preserves_unset_values_and_replaces_ingredients():
    db = Mock()
    recipe = models.Recipe(
        title="Original Ale",
        style="Pale Ale",
        abv=5.0,
        ibu=30,
        description="Original notes",
    )
    recipe.ingredients = [
        models.Ingredient(
            name="Old Hop",
            amount_grams=10,
            ingredient_type="Hop",
        )
    ]

    updated = crud.update_recipe(
        db,
        recipe,
        schemas.RecipeUpdate(
            title="Updated Ale",
            ingredients=[
                schemas.IngredientCreate(
                    name="New Hop",
                    amount_grams=20,
                    ingredient_type="Hop",
                )
            ],
        ),
    )

    assert updated.title == "Updated Ale"
    assert updated.description == "Original notes"
    assert [ingredient.name for ingredient in updated.ingredients] == ["New Hop"]
    db.commit.assert_called_once_with()
    db.refresh.assert_called_once_with(recipe)


def test_feature_flags_use_defaults_and_tenant_override(monkeypatch):
    db = Mock()
    override = models.TenantFeatureFlag(
        tenant_id="tenant-a",
        name="premium_analytics",
        enabled=False,
    )
    db.query.return_value.filter.return_value.all.return_value = [override]
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    flags = crud.get_feature_flags(db, "tenant-a")

    assert flags == {
        "enable_pdf_export": True,
        "enable_ai_suggestions": False,
        "premium_analytics": False,
    }


def test_set_feature_flag_creates_and_updates_flags():
    db = Mock()
    query = db.query.return_value
    query.filter_by.return_value.first.return_value = None

    created = crud.set_feature_flag(db, "tenant-a", "enable_ai_suggestions", True)

    assert created.tenant_id == "tenant-a"
    assert created.name == "enable_ai_suggestions"
    assert created.enabled is True
    db.add.assert_called_once_with(created)
    db.commit.assert_called_once()

    db.reset_mock()
    query.filter_by.return_value.first.return_value = created
    updated = crud.set_feature_flag(db, "tenant-a", "enable_ai_suggestions", False)

    assert updated is created
    assert updated.enabled is False
    db.add.assert_not_called()
    db.commit.assert_called_once()
