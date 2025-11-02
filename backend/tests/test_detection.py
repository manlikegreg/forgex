from backend.api.compiler_engine import detect_language, find_python_entries


def test_detect_python(tmp_path):
    p = tmp_path
    (p / 'requirements.txt').write_text('flask')
    (p / 'app.py').write_text('from flask import Flask\napp = Flask(__name__)')
    lang, scores = detect_language(str(p))
    assert lang == 'python'
    entries = find_python_entries(str(p))
    assert any('app.py' in e[0] for e in entries)
