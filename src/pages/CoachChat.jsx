import React, { useState, useEffect, useRef } from "react";
import { supabase } from "@/api/supabaseClient";
import { useAuth } from "@/lib/AuthContext";
import { Button } from "@/components/ui/button";
import { Loader2, Send, Sparkles, MessageCirclePlus, History, Trash2 } from "lucide-react";
import MessageBubble from "@/components/agent/MessageBubble";
import {
  Drawer, DrawerContent, DrawerHeader, DrawerTitle,
} from "@/components/ui/drawer";
import { useLang } from "@/lib/i18n";

// Заменяет base44.agents.* — разговоры и сообщения теперь лежат в обычных
// таблицах Supabase (agent_conversations / agent_messages), а ответ ассистента
// приходит синхронно из Edge Function 'chat-with-coach' (без polling).

export default function CoachChat() {
  const { t, lang } = useLang();
  const { user } = useAuth();
  const [conversation, setConversation] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState("");
  const [loadingConv, setLoadingConv] = useState(true);
  const [conversations, setConversations] = useState([]);
  const [showHistory, setShowHistory] = useState(false);
  const scrollRef = useRef(null);
  const textareaRef = useRef(null);

  const loadMessages = async (conversationId) => {
    const { data } = await supabase
      .from("agent_messages")
      .select("*")
      .eq("conversation_id", conversationId)
      .order("created_at", { ascending: true });
    setMessages(data || []);
  };

  const loadConversations = async () => {
    const { data } = await supabase
      .from("agent_conversations")
      .select("*")
      .eq("user_id", user?.id)
      .order("updated_at", { ascending: false });
    setConversations(data || []);
    return data || [];
  };

  useEffect(() => {
    if (!user?.id) return;
    (async () => {
      const convs = await loadConversations();
      const conv = convs[0] || null;
      setConversation(conv);
      if (conv) await loadMessages(conv.id);
      setLoadingConv(false);
    })();
  }, [user?.id]);

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [messages]);

  const handleSendText = async (text) => {
    const trimmed = (text ?? input).trim();
    if (!trimmed || sending) return;
    setInput("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
    setSending(true);
    setSendError("");
    // Оптимистично показываем сообщение пользователя сразу
    setMessages((prev) => [...prev, { role: "user", content: trimmed, id: `tmp-${Date.now()}` }]);
    try {
      const { data, error } = await supabase.functions.invoke("chat-with-coach", {
        body: { conversation_id: conversation?.id, message: trimmed, language: lang },
      });
      if (error) {
        const payload = error.context?.clone
          ? await error.context.clone().json().catch(() => null)
          : null;
        throw new Error(payload?.error || error.message || "Chat request failed");
      }
      if (!conversation) {
        // Edge Function создала новый разговор — подтягиваем его
        const convs = await loadConversations();
        const conv = convs.find((c) => c.id === data.conversation_id) || null;
        setConversation(conv);
      }
      await loadMessages(data.conversation_id);
    } catch (error) {
      setSendError(error instanceof Error ? error.message : "Chat request failed");
      setInput(trimmed);
      setMessages((prev) => prev.filter((m) => !String(m.id).startsWith("tmp-")));
    } finally {
      setSending(false);
    }
  };

  const handleSend = () => handleSendText(input);

  const handleNewConversation = () => {
    setConversation(null);
    setMessages([]);
  };

  const selectConversation = async (conv) => {
    setShowHistory(false);
    setLoadingConv(true);
    setConversation(conv);
    await loadMessages(conv.id);
    setLoadingConv(false);
  };

  const convTitle = (conv) => conv.title || t("chat_newChat");

  const deleteConversation = async (e, conv) => {
    e.stopPropagation(); // не открывать этот чат при клике на корзину
    if (!window.confirm(t("chat_deleteConfirm") || "Delete this chat?")) return;
    const { error } = await supabase.from("agent_conversations").delete().eq("id", conv.id);
    if (error) return;
    // agent_messages удалятся каскадно (ON DELETE CASCADE в схеме БД)
    const remaining = conversations.filter((c) => c.id !== conv.id);
    setConversations(remaining);
    if (conversation?.id === conv.id) {
      // Удалили открытый сейчас чат — переключаемся на следующий доступный или на пустой экран
      const next = remaining[0] || null;
      setConversation(next);
      if (next) await loadMessages(next.id);
      else setMessages([]);
    }
  };

  if (loadingConv) {
    return (
      <div className="flex items-center justify-center h-screen">
        <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  const isEmpty = messages.length === 0;
  const suggestions = [t("chat_sugg1"), t("chat_sugg2"), t("chat_sugg3")];

  return (
    <div
      className="flex flex-col overflow-hidden"
      style={{ height: "calc(100dvh - var(--sa-top) - 5rem - var(--sa-bottom))" }}
    >
      <div className="flex items-center justify-between px-4 pt-6 pb-3 border-b border-border">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-full bg-info flex items-center justify-center">
            <Sparkles className="w-4 h-4 text-info-foreground" />
          </div>
          <div>
            <h1 className="text-base font-bold font-heading leading-tight">{t("chat_title")}</h1>
            <p className="text-[11px] text-muted-foreground leading-tight">{t("chat_subtitle")}</p>
          </div>
        </div>
        <div className="flex items-center gap-1">
          <Button variant="ghost" size="icon" className="h-8 w-8 touch-target" onClick={() => { setShowHistory(true); loadConversations(); }}>
            <History className="w-4 h-4" />
          </Button>
          <Button variant="ghost" size="icon" className="h-8 w-8 touch-target" onClick={handleNewConversation}>
            <MessageCirclePlus className="w-4 h-4" />
          </Button>
        </div>
      </div>

      <div ref={scrollRef} className="flex-1 min-h-0 overflow-y-auto overscroll-y-contain px-4 py-4 space-y-3">
        {isEmpty ? (
          <div className="flex flex-col items-center justify-center h-full text-center px-6">
            <div className="w-14 h-14 rounded-2xl bg-info flex items-center justify-center mb-4">
              <Sparkles className="w-7 h-7 text-info-foreground" />
            </div>
            <h2 className="font-semibold font-heading mb-1">{t("chat_emptyTitle")}</h2>
            <p className="text-sm text-muted-foreground mb-6">{t("chat_emptyBody")}</p>
            <div className="space-y-2 w-full max-w-xs">
              {suggestions.map((s) => (
                <button
                  key={s}
                  onClick={() => handleSendText(s)}
                  className="w-full text-left text-sm px-3 py-2.5 rounded-xl border border-border bg-card hover:bg-info hover:border-info-foreground/20 hover:text-info-foreground transition-colors"
                >
                  {s}
                </button>
              ))}
            </div>
            <Button
              onClick={() => handleSendText(t("chat_consultPrompt"))}
              disabled={sending}
              className="mt-2 w-full max-w-xs h-11 rounded-xl text-sm"
            >
              <Sparkles className="w-4 h-4 mr-1.5" />
              {t("chat_consult")}
            </Button>
          </div>
        ) : (
          messages.map((m, idx) => <MessageBubble key={m.id || idx} message={m} />)
        )}
        {sending && (
          <div className="flex justify-start">
            <div className="bg-card border border-border rounded-2xl px-3.5 py-2.5">
              <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
            </div>
          </div>
        )}
      </div>

      <div className="px-4 py-3 border-t border-border bg-card/80 backdrop-blur-sm">
        {sendError && (
          <div role="alert" className="mb-2 rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">
            {sendError}
          </div>
        )}
        <div className="flex gap-2 items-end">
          <textarea
            ref={textareaRef}
            placeholder={t("chat_placeholder")}
            value={input}
            onChange={(e) => {
              setInput(e.target.value);
              e.target.style.height = "auto";
              e.target.style.height = Math.min(e.target.scrollHeight, 120) + "px";
            }}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); } }}
            rows={1}
            className="flex-1 min-h-[44px] max-h-[120px] rounded-xl border border-input bg-background px-3 py-2.5 text-sm resize-none leading-relaxed focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            disabled={sending}
          />
          <Button className="h-11 w-11 p-0 rounded-xl shrink-0" onClick={handleSend} disabled={!input.trim() || sending}>
            <Send className="w-4 h-4" />
          </Button>
        </div>
      </div>

      <Drawer open={showHistory} onOpenChange={setShowHistory}>
        <DrawerContent className="max-w-lg mx-auto">
          <DrawerHeader>
            <DrawerTitle>{t("chat_history")}</DrawerTitle>
          </DrawerHeader>
          <div className="px-4 pb-4 max-h-[60vh] overflow-y-auto space-y-1">
            {conversations.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-6">{t("chat_newChat")}</p>
            ) : (
              conversations.map((c) => {
                const active = c.id === conversation?.id;
                return (
                  <div
                    key={c.id}
                    onClick={() => selectConversation(c)}
                    className={`w-full flex items-center gap-2 text-left px-3 py-2.5 rounded-xl border transition-colors cursor-pointer ${active ? "border-primary bg-info/40" : "border-border bg-card hover:bg-muted"}`}
                  >
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate">{convTitle(c)}</p>
                      {c.created_at && (
                        <p className="text-[11px] text-muted-foreground">{new Date(c.created_at).toLocaleString()}</p>
                      )}
                    </div>
                    <button
                      onClick={(e) => deleteConversation(e, c)}
                      className="shrink-0 h-8 w-8 flex items-center justify-center rounded-lg text-muted-foreground hover:text-destructive hover:bg-destructive/10 touch-target"
                      aria-label={t("chat_deleteChat") || "Delete chat"}
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                );
              })
            )}
          </div>
        </DrawerContent>
      </Drawer>
    </div>
  );
}
