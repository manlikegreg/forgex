# ForgeX Test App (Python)

A minimal FastAPI project to test packaging and env handling.

- Reads environment variables from `.env` (via python-dotenv) and OS environment
- Simple helper module import (`helpers.py`)

## Run locally

```bash
python -m venv .venv
. .venv/Scripts/activate  # Windows PowerShell: .venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

Open http://127.0.0.1:8000/ and http://127.0.0.1:8000/env

## Using with ForgeX
- Project path: the `test` folder
- Language: Python
- Start command: `uvicorn main:app --host 0.0.0.0 --port 8000`
- Include .env: checked
- Optional: set icon file in Home and try advanced PyInstaller options
