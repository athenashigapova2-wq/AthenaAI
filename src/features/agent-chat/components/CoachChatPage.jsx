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
import {
  clearPendingChatJob,
  createChatRequestId,
  loadPendingChatJob,
  savePendingChatJob,
} from "@/features/agent-chat/model/pendingChatJob";

function writeIdempotencyKey(actionId) {
  return `write:${actionId}`;
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
  const recoveredUserRef = useRef(null);
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
    // Leaving or reloading the page only disconnects this browser. The durable
    // Redis job keeps running and is resumed on the next mount.
    activeRequestRef.current?.detach();
  }, []);

  const runPendingJob = async (pending) => {
    setSending(true);
    setSendError("");

    try {
      const request = startAgentMessage({
        conversationId: pending.conversationId,
        jobId: pending.jobId,
        message: pending.message,
        locale: pending.locale,
        requestId: pending.requestId,
        onAccepted: (accepted) => {
          const { message: _sensitiveMessage, ...durablePending } = pending;
          savePendingChatJob(user.id, {
            ...durablePending,
            jobId: accepted.job_id,
          });
        },
        onProgress: setProgress,
      });
      activeRequestRef.current = request;
      const result = await request.promise;
      if (result.pending_write_action) {
        const action = {
          ...result.pending_write_action,
          idempotencyKey: writeIdempotencyKey(result.pending_write_action.action_id),
        };
        setPendingWriteAction(action);
      }
      if (!conversation) {
        const data = await loadConversations();
        setConversation(data.find((item) => item.id === result.conversation_id) || null);
      }
      await loadMessages(result.conversation_id);
      if (!result.pending_write_action) {
        clearPendingChatJob(user.id, pending.requestId);
      }
    } catch (error) {
      const cancelled = error instanceof DOMException && error.name === "AbortError";
      const message = error instanceof Error ? error.message : "Chat request failed";
      const detached = cancelled && message === "Agent request detached";
      const explicitlyCancelled = cancelled && !detached;
      const terminalFailure = error instanceof Error
        && "code" in error
        && error.code === "AGENT_JOB_FAILED";
      const jobGone = error instanceof Error
        && "code" in error
        && error.code === "AGENT_JOB_GONE";
      if (!detached) {
        setSendError(cancelled ? t("chat_cancelled") : agentFetchErrorMessage(message));
      }
      if (explicitlyCancelled || terminalFailure || jobGone) {
        clearPendingChatJob(user.id, pending.requestId);
        if (pending.message) setInput(pending.message);
        setMessages((current) => current.filter(
          (item) => item.id !== `tmp-${pending.requestId}`,
        ));
      }
    } finally {
      activeRequestRef.current = null;
      setProgress(null);
      setSending(false);
    }
  };

  useEffect(() => {
    if (loading || !user?.id || recoveredUserRef.current === user.id) return;
    recoveredUserRef.current = user.id;
    const pending = loadPendingChatJob(user.id);
    if (!pending) return;
    if (pending.message) {
      setMessages((current) => current.some((item) => item.id === `tmp-${pending.requestId}`)
        ? current
        : [...current, {
          role: "user",
          content: pending.message,
          id: `tmp-${pending.requestId}`,
        }]);
    }
    void runPendingJob(pending);
    // Recovery is intentionally attempted once for this mounted user session.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading, user?.id]);

  const sendText = async (text) => {
    const trimmed = (text ?? input).trim();
    if (!trimmed || sending) return;
    setInput("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
    const pending = {
      conversationId: conversation?.id || null,
      jobId: null,
      locale: lang,
      message: trimmed,
      requestId: createChatRequestId(),
    };
    savePendingChatJob(user.id, pending);
    setMessages((current) => [
      ...current,
      { role: "user", content: trimmed, id: `tmp-${pending.requestId}` },
    ]);
    await runPendingJob(pending);
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
      clearPendingChatJob(user.id);
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
      clearPendingChatJob(user.id);
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
