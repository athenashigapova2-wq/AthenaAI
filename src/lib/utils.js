import { clsx } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs) {
  return twMerge(clsx(inputs))
} 


export const isIframe = window.self !== window.top;

// Безопасное "YYYY-MM-DD" без ухода в UTC — d.toISOString() конвертирует
// в UTC и для часовых поясов впереди UTC (Москва и т.д.) сдвигает дату
// на день назад около полуночи. Используем локальные компоненты напрямую.
export function toLocalDateStr(d = new Date()) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}
