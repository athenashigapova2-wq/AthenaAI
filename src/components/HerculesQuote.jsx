import React, { useMemo } from "react";
import { cn } from "@/lib/utils";

const QUOTES = [
  "A true hero is measured by the strength of his heart.",
  "I will go the distance — I'll find my way, if I can be strong.",
  "Sometimes the right path is not the easiest one.",
  "Great deeds are built from small steps taken every day.",
  "Rise to the challenge — your strength lives within you.",
  "A hero's journey begins with a single brave choice.",
  "Fortune favors the bold who keep showing up.",
  "No mountain is too high for the one who keeps climbing.",
];

/**
 * HerculesQuote — a rotating inspirational hero quote in italic display type.
 */
export default function HerculesQuote({ className }) {
  const quote = useMemo(() => QUOTES[Math.floor(Math.random() * QUOTES.length)], []);
  return (
    <blockquote
      className={cn(
        "relative mt-2 border-l-2 border-primary/50 pl-3 italic font-heading text-sm leading-relaxed text-muted-foreground",
        className
      )}
    >
      “{quote}”
    </blockquote>
  );
}