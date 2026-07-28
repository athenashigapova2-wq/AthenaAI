import React, { useState, useEffect, useCallback } from "react";
import { entities } from '@/lib/entities';
import { useAuth } from "@/lib/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import { Loader2, Plus, Trash2, Copy, Check } from "lucide-react";
import { toast } from "@/components/ui/use-toast";
import { useLang } from "@/lib/i18n";

const EMOJI_MAP = [
  ["bread", "🍞"], ["milk", "🥛"], ["cheese", "🧀"], ["yogurt", "🥛"], ["egg", "🥚"],
  ["chicken", "🍗"], ["meat", "🥩"], ["beef", "🥩"], ["pork", "🥓"], ["bacon", "🥓"],
  ["fish", "🐟"], ["salmon", "🐟"], ["tuna", "🐟"], ["shrimp", "🦐"],
  ["rice", "🍚"], ["pasta", "🍝"], ["noodle", "🍜"], ["oat", "🥣"], ["cereal", "🥣"],
  ["tomato", "🍅"], ["carrot", "🥕"], ["broccoli", "🥦"], ["onion", "🧅"], ["garlic", "🧄"],
  ["potato", "🥔"], ["lettuce", "🥬"], ["cabbage", "🥬"], ["spinach", "🥬"], ["cucumber", "🥒"],
  ["pepper", "🫑"], ["corn", "🌽"], ["mushroom", "🍄"], ["avocado", "🥑"],
  ["apple", "🍎"], ["banana", "🍌"], ["orange", "🍊"], ["lemon", "🍋"], ["grape", "🍇"],
  ["berry", "🫐"], ["strawberry", "🍓"], ["pineapple", "🍍"], ["melon", "🍈"], ["peach", "🍑"],
  ["olive", "🫒"], ["oil", "🛢️"], ["butter", "🧈"], ["honey", "🍯"], ["nut", "🥜"], ["almond", "🥜"],
  ["chocolate", "🍫"], ["coffee", "☕"], ["tea", "🍵"], ["water", "💧"], ["juice", "🧃"],
  ["herb", "🌿"], ["basil", "🌿"], ["flour", "🌾"], ["sugar", "🍬"],
  // Russian
  ["хлеб", "🍞"], ["булк", "🍞"], ["молоко", "🥛"], ["кефир", "🥛"], ["сыр", "🧀"],
  ["йогурт", "🥛"], ["яйц", "🥚"], ["куриц", "🍗"], ["мяс", "🥩"], ["говядин", "🥩"],
  ["свинин", "🥓"], ["бекон", "🥓"], ["рыб", "🐟"], ["лосос", "🐟"], ["тунец", "🐟"],
  ["креветк", "🦐"], ["рис", "🍚"], ["макарон", "🍝"], ["лапш", "🍜"], ["овс", "🥣"],
  ["хлопь", "🥣"], ["томат", "🍅"], ["помидор", "🍅"], ["морков", "🥕"], ["брокколи", "🥦"],
  ["лук", "🧅"], ["чеснок", "🧄"], ["картоф", "🥔"], ["капуст", "🥬"], ["шпинат", "🥬"],
  ["салат", "🥬"], ["огурец", "🥒"], ["огурц", "🥒"], ["перец", "🫑"], ["кукуруз", "🌽"],
  ["гриб", "🍄"], ["авокадо", "🥑"], ["яблок", "🍎"], ["банан", "🍌"], ["апельсин", "🍊"],
  ["лимон", "🍋"], ["виноград", "🍇"], ["ягод", "🫐"], ["клубник", "🍓"], ["малин", "🍓"],
  ["ананас", "🍍"], ["дын", "🍈"], ["персик", "🍑"], ["оливк", "🫒"], ["масло", "🧈"],
  ["мёд", "🍯"], ["орех", "🥜"], ["миндаль", "🥜"], ["арахис", "🥜"], ["шоколад", "🍫"],
  ["кофе", "☕"], ["чай", "🍵"], ["вода", "💧"], ["сок", "🧃"], ["зелень", "🌿"],
  ["базилик", "🌿"], ["укроп", "🌿"], ["петрушк", "🌿"], ["мука", "🌾"], ["сахар", "🍬"],
];
const foodEmoji = (name = "") => {
  const n = name.toLowerCase();
  return EMOJI_MAP.find(([k]) => n.includes(k))?.[1] || "🛒";
};

export default function Shopping() {
  const { user } = useAuth();
  const { t } = useLang();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [newItem, setNewItem] = useState("");
  const [copied, setCopied] = useState(false);

  const copyList = async () => {
    const lines = unchecked.map((i) => i.name);
    const text = lines.join("\n");
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      const ta = document.createElement("textarea");
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const loadItems = useCallback(async () => {
    const data = await entities.ShoppingItem.filter({ created_by_id: user?.id });
    setItems(data);
    setLoading(false);
  }, [user]);

  useEffect(() => { loadItems(); }, [loadItems]);

  const addItem = async () => {
    const name = newItem.trim();
    if (!name) return;
    const tempId = `temp-${Date.now()}`;
    setItems((prev) => [...prev, { id: tempId, name, checked: false }]);
    setNewItem("");
    try {
      const created = await entities.ShoppingItem.create({ name, checked: false });
      setItems((prev) => prev.map((i) => (i.id === tempId ? created : i)));
    } catch {
      setItems((prev) => prev.filter((i) => i.id !== tempId));
      toast({ title: t("shop_addErr"), description: t("shop_addErrDesc"), variant: "destructive" });
    }
  };

  const toggleItem = async (item) => {
    const next = !item.checked;
    setItems((prev) => prev.map((i) => (i.id === item.id ? { ...i, checked: next } : i)));
    try {
      await entities.ShoppingItem.update(item.id, { checked: next });
    } catch {
      setItems((prev) => prev.map((i) => (i.id === item.id ? { ...i, checked: item.checked } : i)));
      toast({ title: t("shop_updErr"), variant: "destructive" });
    }
  };

  const deleteItem = async (id) => {
    const removed = items.find((i) => i.id === id);
    setItems((prev) => prev.filter((i) => i.id !== id));
    try {
      await entities.ShoppingItem.delete(id);
    } catch {
      if (removed) setItems((prev) => [...prev, removed]);
      toast({ title: t("shop_delErr"), variant: "destructive" });
    }
  };

  const clearChecked = async () => {
    const checkedItems = items.filter((i) => i.checked);
    setItems((prev) => prev.filter((i) => !i.checked));
    try {
      await Promise.all(checkedItems.map((i) => entities.ShoppingItem.delete(i.id)));
    } catch {
      setItems((prev) => [...prev, ...checkedItems]);
      toast({ title: t("shop_clrErr"), variant: "destructive" });
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  const unchecked = items.filter((i) => !i.checked);
  const checked = items.filter((i) => i.checked);

  return (
    <div className="px-4 pt-6 pb-4 space-y-5">
      <div>
        <h1 className="text-xl font-bold font-heading">{t("shop_title")}</h1>
        <p className="text-sm text-muted-foreground mt-0.5">{t("shop_subtitle")}</p>
      </div>

      <div className="flex gap-2">
        <Input
          placeholder={t("shop_addPh")}
          value={newItem}
          onChange={(e) => setNewItem(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && addItem()}
          className="h-10"
        />
        <Button className="h-10 shrink-0" onClick={addItem} disabled={!newItem.trim()}>
          <Plus className="w-4 h-4" />
        </Button>
      </div>

      {items.length === 0 ? (
        <div className="bg-card rounded-2xl border border-border p-8 text-center">
          <p className="text-sm text-muted-foreground">{t("shop_empty")}</p>
        </div>
      ) : (
        <>
          {unchecked.length > 0 && (
            <div className="space-y-2">
              <Button variant="outline" className="w-full h-10" onClick={copyList} disabled={copied}>
                {copied ? (
                  <><Check className="w-4 h-4 mr-1.5 text-primary" /> {t("shop_copied")}</>
                ) : (
                  <><Copy className="w-4 h-4 mr-1.5" /> {t("shop_copy")}</>
                )}
              </Button>
              <p className="text-[11px] text-muted-foreground text-center -mt-1">{t("shop_copyNote")}</p>
            </div>
          )}
          {unchecked.length > 0 && (
            <div className="bg-card rounded-2xl border border-border divide-y divide-border">
              {unchecked.map((item) => (
                <div key={item.id} className="flex items-center gap-3 px-4 py-3">
                  <Checkbox checked={false} onCheckedChange={() => toggleItem(item)} />
                  <span className="flex-1 text-sm"><span className="mr-1.5">{foodEmoji(item.name)}</span>{item.name}</span>
                  {item.quantity && <span className="text-xs text-muted-foreground">{item.quantity}</span>}
                  <Button variant="ghost" size="icon" className="touch-target h-7 w-7 text-muted-foreground hover:text-destructive" onClick={() => deleteItem(item.id)}>
                    <Trash2 className="w-3.5 h-3.5" />
                  </Button>
                </div>
              ))}
            </div>
          )}

          {checked.length > 0 && (
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-medium text-muted-foreground">{t("shop_done", { n: checked.length })}</span>
                <Button variant="ghost" size="sm" className="h-6 text-xs text-muted-foreground" onClick={clearChecked}>
                  {t("shop_clear")}
                </Button>
              </div>
              <div className="bg-card rounded-2xl border border-border divide-y divide-border opacity-60">
                {checked.map((item) => (
                  <div key={item.id} className="flex items-center gap-3 px-4 py-3">
                    <Checkbox checked onCheckedChange={() => toggleItem(item)} />
                    <span className="flex-1 text-sm line-through"><span className="mr-1.5">{foodEmoji(item.name)}</span>{item.name}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}