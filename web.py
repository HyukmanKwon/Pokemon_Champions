"""내 포켓몬 팀을 로컬 웹으로 보고 고치는 실행 진입점. python web.py 로 띄운다."""
import uvicorn

if __name__ == "__main__":
    uvicorn.run("core.web:app", host="127.0.0.1", port=8000)
