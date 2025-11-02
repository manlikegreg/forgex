export const LANGUAGES = [
  { id: 'python', name: 'Python', description: 'PyInstaller (onefile)' },
]

export const PRESETS: any = {
  python: {
    frameworks: [
      { name: 'Flask', command: 'python app.py' },
      { name: 'FastAPI (uvicorn)', command: 'uvicorn main:app --host 0.0.0.0 --port 8000' },
      { name: 'Django', command: 'python manage.py runserver 0.0.0.0:8000' },
    ],
  },
}
