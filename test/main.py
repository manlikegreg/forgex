import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from fastapi import FastAPI
from helpers import get_greeting

app = FastAPI(title="ForgeX Test App")

APP_MESSAGE = os.getenv("APP_MESSAGE", "Hello from test app")
GREETING_TARGET = os.getenv("GREETING_TARGET", "world")

@app.get("/")
def root():
    return {"message": APP_MESSAGE, "greet": get_greeting(GREETING_TARGET)}

@app.get("/env")
def env_vars():
    return {
        "APP_MESSAGE": APP_MESSAGE,
        "GREETING_TARGET": GREETING_TARGET,
    }

if __name__ == "__main__":
    # Run the FastAPI app when executed as a script or PyInstaller EXE
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    # Use minimal uvicorn config for faster startup and smaller build
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
