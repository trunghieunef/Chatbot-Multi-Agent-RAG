"use client";

import { useChat } from "@/lib/useChat";
import ChatSidebar from "@/components/chatbot/ChatSidebar";
import ChatPanel from "@/components/chatbot/ChatPanel";

export default function TroLyAIPage() {
  const {
    messages,
    input,
    loading,
    sessionId,
    sessions,
    loadingSessions,
    scrollRef,
    setInput,
    send,
    selectSession,
    deleteSession,
    renameSession,
    newSession,
  } = useChat({ mode: "full" });

  return (
    <div className="flex h-[calc(100vh-64px)]">
      {/* Sidebar */}
      <ChatSidebar
        sessions={sessions}
        currentSessionId={sessionId}
        loading={loadingSessions}
        onSelect={selectSession}
        onDelete={deleteSession}
        onRename={renameSession}
        onNew={newSession}
      />

      {/* Main chat area */}
      <div className="flex-1 min-w-0">
        <ChatPanel
          messages={messages}
          input={input}
          loading={loading}
          scrollRef={scrollRef}
          onInputChange={setInput}
          onSend={send}
          hasSession={!!sessionId}
        />
      </div>
    </div>
  );
}
