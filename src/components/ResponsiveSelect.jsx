import React, { useState } from "react";
import { useIsMobile } from "@/hooks/use-mobile";
import { Popover, PopoverTrigger, PopoverContent } from "@/components/ui/popover";
import {
  Drawer,
  DrawerTrigger,
  DrawerContent,
  DrawerHeader,
  DrawerTitle,
} from "@/components/ui/drawer";
import { Check, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * ResponsiveSelect — Radix Popover dropdown on desktop,
 * Vaul bottom-sheet Drawer on mobile.
 *
 * props: value, onValueChange, options:[{value,label}], placeholder, triggerClassName
 */
export default function ResponsiveSelect({
  value,
  onValueChange,
  options,
  placeholder,
  triggerClassName,
}) {
  const isMobile = useIsMobile();
  const [open, setOpen] = useState(false);
  const selected = options.find((o) => o.value === value);
  const label = selected ? selected.label : placeholder || "Select…";

  const triggerClass = cn(
    "flex h-9 w-full items-center justify-between rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring disabled:cursor-not-allowed disabled:opacity-50",
    triggerClassName
  );

  const Option = ({ opt }) => (
    <button
      type="button"
      onClick={() => {
        onValueChange(opt.value);
        setOpen(false);
      }}
      className="flex w-full items-center justify-between rounded-md px-3 py-2.5 text-left text-sm hover:bg-accent transition-colors"
    >
      <span className={cn(opt.value === value && "font-medium")}>{opt.label}</span>
      {opt.value === value && <Check className="w-4 h-4 text-primary" />}
    </button>
  );

  if (isMobile) {
    return (
      <Drawer open={open} onOpenChange={setOpen}>
        <DrawerTrigger asChild>
          <button type="button" className={triggerClass} onClick={() => setOpen(true)}>
            <span className="truncate">{label}</span>
            <ChevronDown className="w-4 h-4 opacity-50 shrink-0" />
          </button>
        </DrawerTrigger>
        <DrawerContent>
          <DrawerHeader className="pb-1">
            <DrawerTitle>{placeholder || "Select an option"}</DrawerTitle>
          </DrawerHeader>
          <div className="px-2 pb-4 max-h-[50vh] overflow-y-auto">
            {options.map((opt) => (
              <Option key={opt.value} opt={opt} />
            ))}
          </div>
        </DrawerContent>
      </Drawer>
    );
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button type="button" className={triggerClass}>
          <span className="truncate">{label}</span>
          <ChevronDown className="w-4 h-4 opacity-50 shrink-0" />
        </button>
      </PopoverTrigger>
      <PopoverContent
        className="p-1 min-w-[8rem] w-[var(--radix-popover-trigger-width)]"
        align="start"
        sideOffset={4}
      >
        <div className="max-h-60 overflow-y-auto">
          {options.map((opt) => (
            <Option key={opt.value} opt={opt} />
          ))}
        </div>
      </PopoverContent>
    </Popover>
  );
}