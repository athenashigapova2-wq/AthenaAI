import React from "react";
import { motion } from "framer-motion";
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { TrendingDown, TrendingUp, Minus } from "lucide-react";
import { useLang } from "@/lib/i18n";

export default function WeightChart({ data }) {
  const { t } = useLang();
  if (data.length === 0) {
    return (
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.4 }}>
        <div className="relative h-[150px] flex items-center justify-center overflow-hidden rounded-xl bg-muted/30">
          <svg className="absolute inset-x-0 top-0 w-full h-full" preserveAspectRatio="none" viewBox="0 0 300 150" fill="none">
            <motion.path
              d="M0,112 C40,102 80,122 120,110 C160,98 200,116 240,106 C270,100 285,108 300,104"
              stroke="hsl(var(--primary))" strokeWidth={2} strokeLinecap="round"
              initial={{ pathLength: 0, opacity: 0.25 }}
              animate={{ pathLength: 1, opacity: 0.5 }}
              transition={{ duration: 1.8, ease: "easeInOut", repeat: Infinity, repeatType: "reverse" }}
            />
          </svg>
          <motion.span
            className="relative z-10 text-xs text-muted-foreground px-3 py-1 rounded-full bg-card/80 backdrop-blur-sm border border-border"
            animate={{ opacity: [0.55, 1, 0.55] }}
            transition={{ duration: 2.6, repeat: Infinity, ease: "easeInOut" }}
          >
            {t("prof_weightEmpty")}
          </motion.span>
        </div>
      </motion.div>
    );
  }

  const first = data[0]?.val;
  const last = data[data.length - 1]?.val;
  const hasDelta = first != null && last != null;
  const delta = hasDelta ? +(last - first).toFixed(1) : null;
  const TrendIcon = delta > 0 ? TrendingUp : delta < 0 ? TrendingDown : Minus;
  const trendColor = delta > 0 ? "text-amber-500" : delta < 0 ? "text-emerald-600" : "text-muted-foreground";

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: "easeOut" }}
    >
      {hasDelta && (
        <div className="flex items-end gap-2 mb-2">
          <span className="text-2xl font-heading font-semibold leading-none">{last}</span>
          <span className="text-xs text-muted-foreground mb-0.5">kg</span>
          <span className={`flex items-center gap-0.5 text-xs font-medium mb-0.5 ml-1 ${trendColor}`}>
            <TrendIcon className="w-3.5 h-3.5" /> {delta > 0 ? "+" : ""}{delta}
          </span>
        </div>
      )}
      <ResponsiveContainer width="100%" height={150}>
        <AreaChart data={data} margin={{ top: 6, right: 6, bottom: 0, left: 6 }}>
          <defs>
            <linearGradient id="weightFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="hsl(var(--primary))" stopOpacity={0.3} />
              <stop offset="100%" stopColor="hsl(var(--primary))" stopOpacity={0} />
            </linearGradient>
          </defs>
          <XAxis dataKey="date" tick={{ fontSize: 10 }} tickLine={false} axisLine={false} dy={6} />
          <YAxis domain={["dataMin - 1", "dataMax + 1"]} hide />
          <Tooltip
            contentStyle={{ fontSize: 12, borderRadius: 10, border: "1px solid hsl(var(--border))", background: "hsl(var(--popover))" }}
            labelStyle={{ color: "hsl(var(--muted-foreground))" }}
            formatter={(v) => [`${v} kg`, t("prof_weightHistory")]}
          />
          <Area
            type="monotone"
            dataKey="val"
            stroke="hsl(var(--primary))"
            strokeWidth={3}
            fill="url(#weightFill)"
            isAnimationActive
            animationDuration={900}
            animationEasing="ease-out"
            dot={{ r: 2.5, fill: "hsl(var(--primary))", strokeWidth: 0 }}
            activeDot={{ r: 5, strokeWidth: 2, stroke: "hsl(var(--background))" }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </motion.div>
  );
}