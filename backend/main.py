from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routes.email_routes import router as email_router

app = FastAPI(title="Personal AI Email Manager")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(email_router)


@app.get("/")
def home():
    return {
        "message": "Personal AI Email Manager is running"
    }