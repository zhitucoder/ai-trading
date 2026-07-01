from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from .routers import screening, backtest, profile, debate, vcp, expert

app = FastAPI(title='AI Trading System')

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

app.include_router(screening.router, prefix='/api/screening', tags=['选股'])
app.include_router(backtest.router, prefix='/api', tags=['回测'])
app.include_router(profile.router, prefix='/api', tags=['画像'])
app.include_router(debate.router, prefix='/api', tags=['辩论'])
app.include_router(vcp.router, prefix='/api/vcp', tags=['VCP'])
app.include_router(expert.router, prefix='/api/expert', tags=['专家'])

web_dir = Path(__file__).resolve().parent.parent.parent / 'web'


@app.get('/api/health')
def health():
    return {'status': 'ok'}


# Serve SPA: API routes declared above, everything else -> index.html
@app.get('/')
@app.get('/{path:path}')
def serve_spa(request: Request, path: str = ''):
    file_path = web_dir / path
    if file_path.is_file() and file_path.suffix in {'.html', '.js', '.css', '.png', '.jpg', '.svg', '.ico'}:
        return FileResponse(str(file_path))
    return HTMLResponse((web_dir / 'index.html').read_text(encoding='utf-8'))
