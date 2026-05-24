import os
os.environ["SUPPRESS_WEBUI_BANNER"] = "true"
import open_tutorai.patches
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from open_webui.main import app as webui_app
from open_webui.config import CORS_ALLOW_ORIGIN
from open_webui.models.users import Users
from open_tutorai.config import AppConfig
from open_tutorai.models.database import init_database

from open_tutorai.routers import (
    response_feedbacks,
    auths,
    supports,
    teacher,
    courses
)

from open_tutorai.env import (
    CHANGELOG,
)

VERSION = "1.0.0"
TUTORAI_BUILD_HASH = os.getenv("TUTORAI_BUILD_HASH", "dev-build")

app = FastAPI(title="Open TutorAI", version=VERSION)

origins = CORS_ALLOW_ORIGIN
allow_origin_regex = None
if "*" in origins:
    origins = []
    allow_origin_regex = ".*"

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=allow_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.state.config = AppConfig()

@app.on_event("startup")
async def startup_db_client():
    try:
        init_database()
        print("Database initialized successfully")
    except Exception as e:
        print(f"Error initializing database: {str(e)}")

@app.post("/tutorai/health")
async def health_check():
    return {"status": "okay"}

app.include_router(response_feedbacks.router, prefix="/api/v1", tags=["response-feedbacks"])
app.include_router(auths.router, prefix="/auths", tags=["auths"])
app.include_router(supports.router, prefix="/api/v1", tags=["supports"])
app.include_router(teacher.router, prefix="/api/v1", tags=["teacher"])
app.include_router(courses.router, prefix="/api/v1", tags=["courses"])

@app.get("/api/changelog")
async def get_app_changelog():
    return {key: CHANGELOG[key] for idx, key in enumerate(CHANGELOG) if idx < 5}

app.mount("/", webui_app)