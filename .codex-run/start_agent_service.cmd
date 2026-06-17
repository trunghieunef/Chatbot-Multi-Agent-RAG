@echo off
cd /d "D:\CODE\RealEstate_Chatbot_v2"
set PYTHONPATH=D:\CODE\RealEstate_Chatbot_v2;D:\CODE\RealEstate_Chatbot_v2\backend
set AGENT_ALLOW_DEV_INTERNAL_KEY=true
"D:\CODE\RealEstate_Chatbot_v2\.venv\Scripts\python.exe" -m uvicorn agent_service.main:app --host 127.0.0.1 --port 8100 >> "D:\CODE\RealEstate_Chatbot_v2\.codex-run\agent_service_8100.out.log" 2>> "D:\CODE\RealEstate_Chatbot_v2\.codex-run\agent_service_8100.err.log"
