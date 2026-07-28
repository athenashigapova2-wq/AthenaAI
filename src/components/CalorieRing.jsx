import React from "react";

export default function CalorieRing({ remaining, target, consumed, label, ofLabel }) {
  const size = 180;
  const strokeWidth = 10;
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const pct = target ? Math.min(consumed / target, 1) : 0;
  const offset = circumference - pct * circumference;

  return (
    <div className="flex flex-col items-center">
      <div className="relative" style={{ width: size, height: size }}>
        <svg width={size} height={size} className="-rotate-90">
          <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="hsl(var(--muted))" strokeWidth={strokeWidth} />
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke="hsl(var(--accent))"
            strokeWidth={strokeWidth}
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            strokeLinecap="round"
            style={{ transition: "stroke-dashoffset 0.6s ease" }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-4xl font-heading leading-none">{Math.round(remaining)}</span>
          <span className="text-xs text-muted-foreground mt-1">{label}</span>
        </div>
      </div>
      <span className="text-[11px] text-muted-foreground mt-2">{ofLabel}</span>
    </div>
  );
}