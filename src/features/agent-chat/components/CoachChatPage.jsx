import { useEffect, useRef, useState } from "react";
import { Loader2 } from "lucide-react";

import { useAuth } from "@/lib/AuthContext";
import { useLang } from "@/lib/i18n";
import {
  agentFetchErrorMessage,
  confirmWriteAction,
  rejectWriteAction,
  startAgentMessage,
} from "@/features/agent-chat/api/agentChatApi";
import {
  fetchConversations,
  fetchMessages,
  removeConversation,
} from "@/features/agent-chat/api/conversationRepository";
import { useAutoScroll } from "@/features/agent-chat/hooks/useAutoScroll";
import ChatComposer from "@/features/agent-chat/components/ChatComposer";
import ChatHeader from "@/features/agent-chat/components/ChatHeader";
import ChatMessages from "@/features/agent-chat/components/ChatMessages";
import ConversationHistoryDrawer from "@/features/agent-chat/components/ConversationHistoryDrawer";

function createIdempotencyKey() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
  const bytes = new Uint8Array(16);
  globalThis.crypto?.getRandomValues?.(bytes);
  const entropy = Array.from(bytes, (value) => value.toString(16).padStart(2, "0")).join("");
  return `write:${Date.now()}:${entropy || "client"}`;
}

export default function CoachChat() {
  const { t, lang } = useLang();
  const { user } = useAuth();
  const [conversation, setConversation] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [progress, setProgress] = useState(null);
  const [sendError, setSendError] = useState("");
  const [loading, setLoading] = useState(true);
  const [pendingWriteAction, setPendingWriteAction] = useState(null);
  const [confirmationBusy, setConfirmationBusy] = useState(false);
  const [confirmationError, setConfirmationError] = useState("");
  const [conversations, setConversations] = useState([]);
  const [showHistory, setShowHistory] = useState(false);
  const textareaRef = useRef(null);
  const activeRequestRef = useRef(null);
  const scrollRef = useAutoScroll(messages);

  const loadMessages = async (conversationId) => {
    setMessages(await fetchMessages(conversationId));
  };

  const loadConversations = async () => {
    const data = await fetchConversations(user?.id);
    setConversations(data);
    return data;
  };

  useEffect(() => {
    if (!user?.id) return;
    let active = true;
    (async () => {
      const data = await fetchConversations(user.id);
      if (!active) return;
      setConversations(data);
      const current = data[0] || null;
      setConversation(current);
      if (current) setMessages(await fetchMessages(current.id));
      if (active) setLoading(false);
    })().catch(() => {
      if (active) setLoading(false);
    });
    return () => {
      active = false;
    };
  }, [user?.id]);

  useEffect(() => () => {
    activeRequestRef.current?.cancel();
  }, []);

  const sendText = async (text) => {
    const trimmed = (text ?? input).trim();
    if (!trimmed || sending) return;
    setInput("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
    setSending(true);
    setSendError("");
    setMessages((current) => [
      ...current,
      { role: "user", content: trimmed, id: `tmp-${Date.now()}` },
    ]);

    try {
      const request = startAgentMessage({
        conversationId: conversation?.id || null,
        message: trimmed,
        locale: lang,
        onProgress: setProgress,
      });
      activeRequestRef.current = request;
      const result = await request.promise;
      if (result.pending_write_action) {
        setPendingWriteAction({
          ...result.pending_write_action,
          idempotencyKey: createIdempotencyKey(),
        });
      }
      if (!conversation) {
        const data = await loadConversations();
        setConversation(data.find((item) => item.id === result.conversation_id) || null);
      }
      await loadMessages(result.conversation_id);
    } catch (error) {
      const cancelled = error instanceof DOMException && error.name === "AbortError";
      const message = error instanceof Error ? error.message : "Chat request failed";
      setSendError(cancelled ? t("chat_cancelled") : agentFetchErrorMessage(message));
      setInput(trimmed);
      setMessages((current) => current.filter((item) => !String(item.id).startsWith("tmp-")));
    } finally {
      activeRequestRef.current = null;
      setProgress(null);
      setSending(false);
    }
  };

  const confirmPendingWrite = async () => {
    if (!pendingWriteAction || confirmationBusy) return;
    setConfirmationBusy(true);
    setConfirmationError("");
    try {
      const result = await confirmWriteAction(
        pendingWriteAction,
        pendingWriteAction.idempotencyKey,
      );
      setPendingWriteAction(null);
      if (result.conversation_id) await loadMessages(result.conversation_id);
    } catch (error) {
      setConfirmationError(error instanceof Error ? error.message : t("chat_writeFailed"));
    } finally {
      setConfirmationBusy(false);
    }
  };

  const rejectPendingWrite = async () => {
    if (!pendingWriteAction || confirmationBusy) return;
    setConfirmationBusy(true);
    setConfirmationError("");
    try {
      await rejectWriteAction(pendingWriteAction);
      setPendingWriteAction(null);
    } catch (error) {
      setConfirmationError(error instanceof Error ? error.message : t("chat_writeFailed"));
    } finally {
      setConfirmationBusy(false);
    }
  };

  const selectConversation = async (selected) => {
    setShowHistory(false);
    setLoading(true);
    setConversation(selected);
    await loadMessages(selected.id);
    setLoading(false);
  };

  const deleteConversation = async (event, selected) => {
    event.stopPropagation();
    if (!window.confirm(t("chat_deleteConfirm") || "Delete this chat?")) return;
    try {
      await removeConversation(selected.id);
    } catch {
      return;
    }
    const remaining = conversations.filter((item) => item.id !== selected.id);
    setConversations(remaining);
    if (conversation?.id === selected.id) {
      const next = remaining[0] || null;
      setConversation(next);
      if (next) await loadMessages(next.id);
      else setMessages([]);
    }
  };

  if (loading) {
    return <div className="flex h-screen items-center justify-center"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>;
  }

  return (
    <div className="flex flex-col overflow-hidden" style={{ height: "calc(100dvh - var(--sa-top) - 5rem - var(--sa-bottom))" }}>
      <ChatHeader
        t={t}
        onHistory={() => {
          setShowHistory(true);
          loadConversations();
        }}
        onNewConversation={() => {
          setConversation(null);
          setMessages([]);
        }}
      />
      <ChatMessages
        messages={messages}
        sending={sending}
        progress={progress}
        suggestions={[t("chat_sugg1"), t("chat_sugg2"), t("chat_sugg3")]}
        t={t}
        onSuggestion={sendText}
        onCancel={() => activeRequestRef.current?.cancel()}
        pendingWriteAction={pendingWriteAction}
        confirmationBusy={confirmationBusy}
        confirmationError={confirmationError}
        onConfirmWrite={confirmPendingWrite}
        onRejectWrite={rejectPendingWrite}
        scrollRef={scrollRef}
      />
      <ChatComposer
        input={input}
        sending={sending}
        error={sendError}
        t={t}
        textareaRef={textareaRef}
        onChange={setInput}
        onSend={() => sendText(input)}
      />
      <ConversationHistoryDrawer
        open={showHistory}
        onOpenChange={setShowHistory}
        conversations={conversations}
        activeId={conversation?.id}
        t={t}
        onSelect={selectConversation}
        onDelete={deleteConversation}
      />
    </div>
  );
}
