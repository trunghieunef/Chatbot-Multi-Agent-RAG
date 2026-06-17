@echo off
cd /d "D:\CODE\RealEstate_Chatbot_v2\frontend"
set INTERNAL_API_URL=http://localhost:8000
set NEXT_PUBLIC_API_URL=/api/v1
npm.cmd run dev >> "D:\CODE\RealEstate_Chatbot_v2\.codex-run\frontend_3000.out.log" 2>> "D:\CODE\RealEstate_Chatbot_v2\.codex-run\frontend_3000.err.log"
