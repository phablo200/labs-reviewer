import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from core.auth import router as auth_router
from core.database.mongodb import close_mongodb, init_mongodb
from core.middleware.required_headers import RequiredHeadersMiddleware
from labs.agents import router as lab_post
from labs.process_status.routers import agent_router as agent_process_status_router
from labs.process_status.routers import process_status_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_mongodb()
    yield
    await close_mongodb()


app = FastAPI(title="MeBrain Agents API", lifespan=lifespan)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

FRONTEND_ORIGINS = [
    "http://localhost:4004",
    "http://127.0.0.1:4004",
    "http://localhost:4009",
    "http://localhost:4010",
    "http://127.0.0.1:4009",
    "http://localhost:8080",
    "http://127.0.0.1:8080",
    "http://localhost:5173",
    "http://127.0.0.1:5173"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequiredHeadersMiddleware)

app.include_router(lab_post.router)
app.include_router(lab_post.outputs_router)
app.include_router(process_status_router.router)
app.include_router(agent_process_status_router.agent_process_router)
app.include_router(auth_router.router)


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "LabsReview Agents API is running 🚀"}
