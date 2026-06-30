import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from src.routers import screen

app = FastAPI(title='AI股票分析系统', docs_url='/docs')

app.include_router(screen.router)

frontend_dir = os.path.join(os.path.dirname(__file__), 'frontend')
app.mount('/static', StaticFiles(directory=frontend_dir), name='static')


@app.get('/')
def index():
    return FileResponse(os.path.join(frontend_dir, 'index.html'))


if __name__ == '__main__':
    import uvicorn
    uvicorn.run('src.main:app', host='0.0.0.0', port=9000, reload=False)
