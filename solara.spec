# PyInstaller recipe for Solara.exe (Windows): pyinstaller --noconfirm solara.spec
# Output: dist/Solara/Solara.exe with its _internal folder. Copy the whole dist/Solara folder.
# The data folder, solara.env and logs live beside Solara.exe and are never inside the build.
from PyInstaller.utils.hooks import collect_all

datas = [("web", "web"), ("extension", "extension"), ("docs/RUNNING.md", "docs")]
binaries, hidden = [], ["app.main", "uvicorn.logging", "uvicorn.loops.auto", "uvicorn.protocols.http.auto",
                        "uvicorn.protocols.websockets.auto", "uvicorn.lifespan.on"]
for pkg in ("playwright", "zxingcpp", "fitz", "pymupdf", "qrcode", "openpyxl", "pypdf"):
    try:
        d, b, h = collect_all(pkg)
        datas += d; binaries += b; hidden += h
    except Exception:
        pass

a = Analysis(["app/launcher.py"], pathex=["."], binaries=binaries, datas=datas, hiddenimports=hidden,
             # whatever else this computer's Python has installed stays out: Solara uses none of it
             excludes=["tkinter", "pytest", "transformers", "torch", "tensorflow", "keras", "jax", "scipy", "pandas",
                       "matplotlib", "sklearn", "IPython", "jupyter", "notebook", "numba", "sympy", "cv2", "onnxruntime",
                       "datasets", "huggingface_hub", "tokenizers", "nltk", "spacy", "boto3", "botocore", "grpc",
                       "google", "anthropic", "openai", "langchain", "sqlalchemy", "pyarrow", "polars"],
             noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Solara", console=False, icon=None)
coll = COLLECT(exe, a.binaries, a.datas, name="Solara")
