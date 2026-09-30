from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routes.email_routes import router as email_router


app = FastAPI(
    title="Personal AI Email Manager"
)


# ============================================================
# CORS
# ============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# EMAIL ROUTES
# ============================================================

app.include_router(email_router)


# ============================================================
# HOME
# ============================================================

@app.get("/")
def home():
    return {
        "message": "Personal AI Email Manager is running"
    }


# ============================================================
# HEALTH CHECK
# ============================================================

@app.get("/healthz")
def healthz():
    return {
        "status": "healthy",
        "service": "Personal AI Email Manager"
    }