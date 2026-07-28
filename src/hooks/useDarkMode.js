import { useEffect } from "react";

/**
 * Syncs the app's dark mode with the user's system preference.
 * Adds/removes the `dark` class on <html> dynamically.
 */
export function useDarkMode() {
  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const apply = () => {
      document.documentElement.classList.toggle("dark", mq.matches);
    };
    apply();
    const listener = (e) => apply();
    mq.addEventListener("change", listener);
    return () => mq.removeEventListener("change", listener);
  }, []);
}