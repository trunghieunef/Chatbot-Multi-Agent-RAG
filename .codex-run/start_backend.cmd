@echo off
cd /d "D:\CODE\RealEstate_Chatbot_v2\backend"
set PYTHONPATH=D:\CODE\RealEstate_Chatbot_v2;D:\CODE\RealEstate_Chatbot_v2\backend
set CHATBOT_AGENT_SERVICE_ENABLED=false
"D:\CODE\RealEstate_Chatbot_v2\.venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 >> "D:\CODE\RealEstate_Chatbot_v2\.codex-run\backend_8000.out.log" 2>> "D:\CODE\RealEstate_Chatbot_v2\.codex-run\backend_8000.err.log"
