from fastapi import FastAPI
from api.routes import router as root_router

app = FastAPI(title="Aethelred API")
app.include_router(root_router)
