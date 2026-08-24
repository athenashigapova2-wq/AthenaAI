import { Link } from "react-router-dom";
import { Activity, History, MessageCirclePlus, Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";

export default function ChatHeader({ t, onHistory, onNewConversation }) {
  return (
    <div className="flex items-center justify-between border-b border-border px-4 pb-3 pt-6">
      <div className="flex items-center gap-2">
        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-info">
          <Sparkles className="h-4 w-4 text-info-foreground" />
        </div>
        <div>
          <h1 className="font-heading text-base font-bold leading-tight">{t("chat_title")}</h1>
          <p className="text-[11px] leading-tight text-muted-foreground">{t("chat_subtitle")}</p>
        </div>
      </div>
      <div className="flex items-center gap-1">
        <Button asChild variant="ghost" size="icon" className="touch-target h-8 w-8">
          <Link to="/observability" aria-label="Open agent observability dashboard" title="Agent traces">
            <Activity className="h-4 w-4" />
          </Link>
        </Button>
        <Button variant="ghost" size="icon" className="touch-target h-8 w-8" onClick={onHistory}>
          <History className="h-4 w-4" />
        </Button>
        <Button variant="ghost" size="icon" className="touch-target h-8 w-8" onClick={onNewConversation}>
          <MessageCirclePlus className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
