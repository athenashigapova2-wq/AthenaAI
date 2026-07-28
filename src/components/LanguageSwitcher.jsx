import React from "react";
import { useLang, LANGS } from "@/lib/i18n";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
} from "@/components/ui/dropdown-menu";
import { Globe } from "lucide-react";

export default function LanguageSwitcher({ compact = false }) {
  const { lang, setLang } = useLang();
  const cur = LANGS.find((l) => l.code === lang) || LANGS[0];
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="sm" className="touch-target h-8 gap-1.5 px-2 text-xs">
          <Globe className="w-4 h-4" />
          <span className="text-base leading-none">{cur.flag}</span>
          {!compact && <span className="hidden sm:inline">{cur.label}</span>}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-[180px]">
        {LANGS.map((l) => (
          <DropdownMenuItem
            key={l.code}
            onClick={() => setLang(l.code)}
            className={`gap-2 ${l.code === lang ? "bg-accent/10 text-accent" : ""}`}
          >
            <span className="text-base leading-none">{l.flag}</span>
            {l.label}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}