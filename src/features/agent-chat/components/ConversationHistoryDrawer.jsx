import { Trash2 } from "lucide-react";

import { Drawer, DrawerContent, DrawerHeader, DrawerTitle } from "@/components/ui/drawer";

export default function ConversationHistoryDrawer({ open, onOpenChange, conversations, activeId, t, onSelect, onDelete }) {
  return (
    <Drawer open={open} onOpenChange={onOpenChange}>
      <DrawerContent className="mx-auto max-w-lg">
        <DrawerHeader><DrawerTitle>{t("chat_history")}</DrawerTitle></DrawerHeader>
        <div className="max-h-[60vh] space-y-1 overflow-y-auto px-4 pb-4">
          {conversations.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">{t("chat_newChat")}</p>
          ) : conversations.map((conversation) => (
            <div
              key={conversation.id}
              onClick={() => onSelect(conversation)}
              className={`flex w-full cursor-pointer items-center gap-2 rounded-xl border px-3 py-2.5 text-left transition-colors ${conversation.id === activeId ? "border-primary bg-info/40" : "border-border bg-card hover:bg-muted"}`}
            >
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">{conversation.title || t("chat_newChat")}</p>
                {conversation.created_at && <p className="text-[11px] text-muted-foreground">{new Date(conversation.created_at).toLocaleString()}</p>}
              </div>
              <button
                onClick={(event) => onDelete(event, conversation)}
                className="touch-target flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
                aria-label={t("chat_deleteChat") || "Delete chat"}
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
          ))}
        </div>
      </DrawerContent>
    </Drawer>
  );
}
