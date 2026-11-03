import os
import json
import secrets
import shutil
import uuid
from pathlib import Path
from typing import Optional
from urllib.parse import quote
from contextlib import AsyncExitStack
import boto3
import httpx
import redis
from mcp.shared.exceptions import McpError
from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File, Query, Form, Header
from fastapi import Request
from fastapi.responses import FileResponse, RedirectResponse, Response, StreamingResponse
from fastapi.security import OAuth2PasswordRequestForm
from authlib.integrations.base_client.errors import OAuthError
from authlib.integrations.starlette_client import OAuth
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from . import models, schemas, database, auth, crud, seo
from .mcp_agent import (
    READ_ONLY_TOOL_NAMES,
    call_read_tool,
    connect_to_mcp,
    gemini_function_declarations,
)
from .telegram import send_telegram_notification
from .worker import process_recipe_file_task, send_telegram_notification_task

models.Base.metadata.create_all(bind=database.engine)

with database.SessionLocal() as startup_db:
    legacy_users = startup_db.query(models.User).filter(
        (models.User.tenant_id == "default") | (models.User.tenant_id.is_(None))
    )
    for legacy_user in legacy_users:
        legacy_user.tenant_id = str(uuid.uuid4())
    startup_db.commit()

app = FastAPI(title="Akatosh API - Beer Recipe Book", version="1.0.0")
allowed_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
]
if allowed_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )
app.add_middleware(
    SessionMiddleware,
    secret_key=auth.SECRET_KEY,
    same_site="lax",
    https_only=os.getenv("SESSION_HTTPS_ONLY", "false").lower() == "true",
)
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
app.mount(
    "/assets",
    StaticFiles(directory=FRONTEND_DIR / "assets"),
    name="frontend-assets",
)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)

@app.get("/health", status_code=status.HTTP_200_OK)
def health_check():
    return {"status": "healthy", "app": "akatosh"}

@app.get("/")
def root():
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/config.js")
def frontend_config():
    settings = {
        "googleAnalyticsId": os.getenv("GOOGLE_ANALYTICS_ID", ""),
        "apiBaseUrl": os.getenv("PUBLIC_API_BASE_URL", ""),
        "aiAssistantConfigured": bool(os.getenv("GEMINI_API_KEY")),
    }
    return Response(
        f"window.APP_CONFIG = {json.dumps(settings)};",
        media_type="application/javascript",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/robots.txt")
def robots_txt(request: Request):
    base_url = os.getenv("PUBLIC_SITE_URL", str(request.base_url)).rstrip("/")
    return Response(seo.build_robots_txt(base_url), media_type="text/plain")


@app.get("/sitemap.xml")
def sitemap_xml(request: Request):
    base_url = os.getenv("PUBLIC_SITE_URL", str(request.base_url).rstrip("/"))
    return Response(seo.build_sitemap_xml(base_url), media_type="application/xml")


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


def get_google_oauth_client():
    secret_key = os.getenv("SECRET_KEY")
    required_settings = (
        os.getenv("GOOGLE_CLIENT_ID"),
        os.getenv("GOOGLE_CLIENT_SECRET"),
        os.getenv("GOOGLE_REDIRECT_URI"),
    )
    if (
        not all(required_settings)
        or not secret_key
        or len(secret_key) < 32
    ):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google sign-in is not configured",
        )

    oauth = OAuth()
    oauth.register(
        name="google",
        client_id=required_settings[0],
        client_secret=required_settings[1],
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )
    return oauth.create_client("google")


@app.get("/auth/google/login")
async def google_login(request: Request):
    google = get_google_oauth_client()
    return await google.authorize_redirect(
        request, redirect_uri=os.environ["GOOGLE_REDIRECT_URI"]
    )


@app.get("/auth/google/callback")
async def google_callback(
    request: Request,
    db: Session = Depends(database.get_db),
):
    google = get_google_oauth_client()
    try:
        token = await google.authorize_access_token(request)
    except OAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google sign-in failed",
        ) from exc

    user_info = token.get("userinfo")
    email = user_info.get("email") if user_info else None
    if not email or user_info.get("email_verified") is not True:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google did not provide a verified email address",
        )

    user = crud.get_user_by_email(db, email)
    if user is None:
        user = crud.create_user(
            db,
            schemas.UserCreate(email=email, password=uuid.uuid4().hex),
        )

    access_token = auth.create_access_token(data={"sub": user.email})
    frontend_url = os.getenv("PUBLIC_SITE_URL", str(request.base_url)).rstrip("/")
    return RedirectResponse(
        f"{frontend_url}/#access_token={quote(access_token, safe='')}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@app.get("/features/")
def get_feature_flags(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db),
):
    return {
        "tenant_id": current_user.tenant_id,
        "flags": crud.get_feature_flags(db, current_user.tenant_id),
    }

def require_feature_admin(
    token: Optional[str] = Header(default=None, alias="X-Feature-Admin-Token"),
) -> None:
    expected_token = os.getenv("FEATURE_ADMIN_TOKEN")
    if not expected_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Feature administration is not configured",
        )
    if token is None or not secrets.compare_digest(token, expected_token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Feature administrator credentials required",
        )


@app.put("/features/{feature_name}")
def update_feature_flag(
    feature_name: str,
    update: schemas.FeatureFlagUpdate,
    current_user: models.User = Depends(auth.get_current_user),
    _: None = Depends(require_feature_admin),
    db: Session = Depends(database.get_db),
):
    allowed_features = {
        "enable_pdf_export",
        "enable_ai_suggestions",
        "premium_analytics",
    }
    if feature_name not in allowed_features:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown feature")
    flag = crud.set_feature_flag(
        db, current_user.tenant_id, feature_name, update.enabled
    )
    return {
        "tenant_id": flag.tenant_id,
        "name": flag.name,
        "enabled": bool(flag.enabled),
    }


@app.get("/tenant/info")
def get_tenant_info(current_user: models.User = Depends(auth.get_current_user)):
    return {
        "user_email": current_user.email,
        "tenant_id": current_user.tenant_id,
        "message": f"Data isolated for tenant: {current_user.tenant_id}",
    }


def invalidate_recipe_cache() -> None:
    try:
        for key in redis_client.scan_iter("recipes_*"):
            redis_client.delete(key)
    except Exception as exc:
        print(f"Redis cache invalidation error: {exc}")


def save_recipe_upload(file: UploadFile) -> str:
    filename = os.path.basename(file.filename or "upload")
    key = f"recipes/{uuid.uuid4().hex}_{filename}"
    bucket = os.getenv("AWS_S3_BUCKET")
    if bucket:
        s3 = boto3.client("s3", region_name=os.getenv("AWS_REGION"))
        s3.upload_fileobj(
            file.file,
            bucket,
            key,
            ExtraArgs={"ContentType": file.content_type or "application/octet-stream"},
        )
        return f"s3://{bucket}/{key}"

    os.makedirs("uploads", exist_ok=True)
    local_path = Path("uploads") / f"{uuid.uuid4().hex}_{filename}"
    with local_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    return str(local_path)


@app.post("/recipes/", response_model=schemas.RecipeResponse, status_code=status.HTTP_201_CREATED)
def create_recipe(
    title: str = Form(...),
    style: str = Form(...),
    abv: float = Form(...),
    ibu: int = Form(...),
    description: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db)
):
    file_path = None
    if file:
        try:
            file_path = save_recipe_upload(file)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Recipe file could not be stored",
            ) from exc

    recipe = crud.create_recipe(db, title, style, abv, ibu, description, file_path, current_user.id)

    if file_path:
        process_recipe_file_task.delay(file_path, recipe.title)
    send_telegram_notification_task.delay(recipe.title, recipe.style, recipe.abv)

    invalidate_recipe_cache()

    return recipe

@app.get("/recipes/", response_model=schemas.PaginatedRecipesResponse)
def list_recipes(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db)
):
    tenant_id = current_user.tenant_id
    cache_key = f"recipes_tenant_{tenant_id}_skip_{skip}_limit_{limit}"
    try:
        cached = redis_client.get(cache_key)
        if cached:
            return json.loads(cached)
    except Exception as e:
        print(f"Redis cache read error: {e}")

    recipes = crud.get_recipes(db, tenant_id, skip=skip, limit=limit)
    total = crud.get_recipes_count(db, tenant_id)
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
        redis_client.set(cache_key, json.dumps(response_data), ex=60)
    except Exception as e:
        print(f"Redis cache write error: {e}")

    return response_data


@app.get("/api/recipes/{recipe_id}/file")
def get_recipe_file(
    recipe_id: int,
    redirect: bool = Query(True),
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db),
):
    recipe = crud.get_recipe(db, recipe_id, current_user.tenant_id)
    if recipe is None or not recipe.file_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Recipe file not found"
        )
    if recipe.file_path.startswith("s3://"):
        bucket, _, key = recipe.file_path[5:].partition("/")
        if not bucket or not key or not os.getenv("AWS_S3_BUCKET"):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Recipe file storage is not configured",
            )
        try:
            url = boto3.client("s3", region_name=os.getenv("AWS_REGION")).generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket, "Key": key},
                ExpiresIn=300,
            )
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Recipe file could not be retrieved",
            ) from exc
        if not redirect:
            return {"download_url": url}
        return RedirectResponse(url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    local_path = Path(recipe.file_path).resolve()
    upload_dir = (Path.cwd() / "uploads").resolve()
    if not local_path.is_relative_to(upload_dir) or not local_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Recipe file not found"
        )
    return FileResponse(local_path)


@app.post(
    "/api/recipes/{recipe_id}/file",
    response_model=schemas.RecipeResponse,
    status_code=status.HTTP_201_CREATED,
)
def upload_recipe_file(
    recipe_id: int,
    file: UploadFile = File(...),
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db),
):
    recipe = crud.get_recipe(db, recipe_id, current_user.tenant_id)
    if recipe is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Recipe not found"
        )
    try:
        recipe.file_path = save_recipe_upload(file)
        db.commit()
        db.refresh(recipe)
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Recipe file could not be stored",
        ) from exc
    return recipe


def assistant_error(message: str) -> str:
    return f"event: error\ndata: {json.dumps({'error': message})}\n\n"


def assistant_progress(message: str) -> str:
    return f"event: progress\ndata: {json.dumps({'message': message})}\n\n"


async def stream_gemini_response(prompt: str, tenant_id: str):
    api_key = os.getenv("GEMINI_API_KEY")
    model_name = os.getenv("GEMINI_MODEL") or "gemini-3.6-flash"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:streamGenerateContent"
    yield assistant_progress("Connecting to Gemini…")
    try:
        async with AsyncExitStack() as stack:
            mcp_session = None
            declarations = []
            if os.getenv("MCP_AGENT_ENABLED", "").lower() == "true":
                yield assistant_progress("Connecting to tenant recipe tools…")
                try:
                    mcp_session = await stack.enter_async_context(
                        connect_to_mcp(tenant_id)
                    )
                    tools = await mcp_session.list_tools()
                except (McpError, OSError, RuntimeError):
                    yield assistant_error("The tenant recipe tools are unavailable.")
                    return
                declarations = gemini_function_declarations(tools.tools)
                if not declarations:
                    raise RuntimeError("The MCP server exposes no read-only recipe tools")
                yield assistant_progress("Connected to read-only recipe tools.")

            contents = [{"role": "user", "parts": [{"text": prompt}]}]
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(60.0, connect=10.0)
            ) as client:
                for turn in range(4):
                    payload = {"contents": contents}
                    if declarations:
                        payload["tools"] = [{"functionDeclarations": declarations}]
                        payload["systemInstruction"] = {
                            "parts": [
                                {
                                    "text": (
                                        "Use read-only recipe tools when the question asks "
                                        "about this user's saved recipes or ingredients. "
                                        "Do not invent recipe data."
                                    )
                                }
                            ]
                        }

                    yield assistant_progress("Gemini is generating a response…")
                    async with client.stream(
                        "POST",
                        url,
                        params={"alt": "sse"},
                        headers={"x-goog-api-key": api_key},
                        json=payload,
                    ) as response:
                        if response.is_error:
                            if response.status_code in {401, 403}:
                                message = (
                                    "Gemini rejected the API key or the key lacks API access "
                                    f"(HTTP {response.status_code}). Check the key and its "
                                    "Google AI API permissions."
                                )
                            elif response.status_code == 404:
                                message = (
                                    f"Gemini model '{model_name}' was not found (HTTP 404). "
                                    "Check GEMINI_MODEL."
                                )
                            elif response.status_code == 429:
                                message = (
                                    "Gemini quota or rate limit reached (HTTP 429). "
                                    "Check the project's API quota."
                                )
                            elif response.status_code == 402:
                                message = (
                                    "Gemini requires payment or the project's prepaid "
                                    "credits may be depleted (HTTP 402). Check the "
                                    "Google AI Studio billing page and the billing "
                                    "status of the project that owns this API key. "
                                    "Creating another key in the same project may not help."
                                )
                            else:
                                message = (
                                    "Gemini could not complete the request "
                                    f"(HTTP {response.status_code})."
                                )
                            await response.aread()
                            yield assistant_error(message)
                            return

                        model_parts = []
                        function_calls = []
                        async for line in response.aiter_lines():
                            if not line.startswith("data: "):
                                continue
                            data = line[6:]
                            if data == "[DONE]":
                                continue
                            try:
                                chunk = json.loads(data)
                                parts = [
                                    part
                                    for candidate in chunk.get("candidates", [])
                                    for part in candidate.get("content", {}).get("parts", [])
                                ]
                            except (json.JSONDecodeError, AttributeError, TypeError):
                                yield assistant_error(
                                    "The AI provider returned an invalid response."
                                )
                                return
                            for part in parts:
                                if "text" in part:
                                    model_parts.append({"text": part["text"]})
                                    yield f"data: {json.dumps({'text': part['text']})}\n\n"
                                elif "functionCall" in part:
                                    function_call = part["functionCall"]
                                    model_parts.append({"functionCall": function_call})
                                    function_calls.append(function_call)

                    if not function_calls:
                        yield "event: done\ndata: {}\n\n"
                        return
                    if mcp_session is None or turn == 3:
                        yield assistant_error("The assistant reached its MCP tool-call limit.")
                        return

                    contents.append({"role": "model", "parts": model_parts})
                    for function_call in function_calls:
                        name = function_call.get("name", "")
                        if name not in READ_ONLY_TOOL_NAMES:
                            yield assistant_error(
                                f"The assistant requested an unavailable MCP tool: {name}."
                            )
                            return
                        yield assistant_progress(
                            f"Using recipe tool: {name.replace('_', ' ')}…"
                        )
                        try:
                            result = await call_read_tool(
                                mcp_session,
                                name,
                                function_call.get("args", {}),
                            )
                        except (McpError, OSError, RuntimeError, ValueError) as exc:
                            yield assistant_error(str(exc))
                            return
                        contents.append(
                            {
                                "role": "user",
                                "parts": [
                                    {
                                        "functionResponse": {
                                            "name": name,
                                            "response": {"result": result},
                                        }
                                    }
                                ],
                            }
                        )
    except httpx.HTTPError:
        yield assistant_error("The AI provider is temporarily unavailable.")


@app.post("/api/assistant/stream")
def stream_assistant_response(
    request_data: schemas.AssistantPrompt,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db),
):
    if not crud.get_feature_flags(db, current_user.tenant_id)["enable_ai_suggestions"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="AI suggestions are disabled for this tenant",
        )
    if not os.getenv("GEMINI_API_KEY"):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI suggestions are not configured",
        )
    return StreamingResponse(
        stream_gemini_response(request_data.prompt, current_user.tenant_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post(
    "/api/recipes/",
    response_model=schemas.RecipeResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_recipe_json(
    recipe_data: schemas.RecipeCreate,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db),
):
    recipe = crud.create_recipe(
        db,
        recipe_data.title,
        recipe_data.style,
        recipe_data.abv,
        recipe_data.ibu,
        recipe_data.description,
        None,
        current_user.id,
        recipe_data.ingredients,
    )
    if os.getenv("RABBITMQ_URL"):
        send_telegram_notification_task.delay(
            recipe.title, recipe.style, recipe.abv
        )
    else:
        send_telegram_notification(recipe.title, recipe.style, recipe.abv)
    invalidate_recipe_cache()
    return recipe


@app.get("/api/recipes/", response_model=schemas.PaginatedRecipesResponse)
def list_recipes_json(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db),
):
    tenant_id = current_user.tenant_id
    cache_key = f"recipes_api_tenant_{tenant_id}_skip_{skip}_limit_{limit}"
    try:
        cached = redis_client.get(cache_key)
        if cached:
            return json.loads(cached)
    except Exception as exc:
        print(f"Redis cache read error: {exc}")

    recipes = crud.get_recipes(db, tenant_id, skip=skip, limit=limit)
    total = crud.get_recipes_count(db, tenant_id)
    next_skip = skip + limit
    response_data = {
        "items": [
            schemas.RecipeResponse.model_validate(recipe).model_dump(mode="json")
            for recipe in recipes
        ],
        "total": total,
        "skip": skip,
        "limit": limit,
        "next_link": (
            f"/api/recipes/?skip={next_skip}&limit={limit}"
            if next_skip < total
            else None
        ),
    }

    try:
        redis_client.set(cache_key, json.dumps(response_data), ex=60)
    except Exception as exc:
        print(f"Redis cache write error: {exc}")

    return response_data


@app.get("/api/recipes/{recipe_id}", response_model=schemas.RecipeResponse)
def get_recipe_json(
    recipe_id: int,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db),
):
    recipe = crud.get_recipe(db, recipe_id, current_user.tenant_id)
    if recipe is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Recipe not found"
        )
    return recipe


@app.put("/api/recipes/{recipe_id}", response_model=schemas.RecipeResponse)
def update_recipe_json(
    recipe_id: int,
    recipe_data: schemas.RecipeUpdate,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db),
):
    recipe = crud.get_recipe(db, recipe_id, current_user.tenant_id)
    if recipe is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Recipe not found"
        )
    updated = crud.update_recipe(db, recipe, recipe_data)
    invalidate_recipe_cache()
    return updated


@app.delete("/api/recipes/{recipe_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_recipe_json(
    recipe_id: int,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db),
):
    recipe = crud.get_recipe(db, recipe_id, current_user.tenant_id)
    if recipe is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Recipe not found"
        )
    crud.delete_recipe(db, recipe)
    invalidate_recipe_cache()