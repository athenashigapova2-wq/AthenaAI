import { useEffect, useRef, useState } from "react";

/**
 * Lightweight pull-to-refresh for touch devices.
 * Attaches to window scroll; only activates when the page is scrolled to the top.
 *
 * @param {Function} onRefresh - async function called when a pull passes the threshold
 * @param {Object} opts - { threshold: px to trigger, max: px clamp }
 * @returns {{ pullDistance: number, refreshing: boolean }}
 */
export function usePullToRefresh(onRefresh, { threshold = 70, max = 110 } = {}) {
  const [pullDistance, setPullDistance] = useState(0);
  const [refreshing, setRefreshing] = useState(false);
  const startY = useRef(0);
  const pulling = useRef(false);
  const onRefreshRef = useRef(onRefresh);
  onRefreshRef.current = onRefresh;

  useEffect(() => {
    const onTouchStart = (e) => {
      if (window.scrollY > 0 || refreshing) return;
      startY.current = e.touches[0].clientY;
      pulling.current = true;
    };

    const onTouchMove = (e) => {
      if (!pulling.current || refreshing) return;
      const dy = e.touches[0].clientY - startY.current;
      if (dy <= 0) {
        setPullDistance(0);
        return;
      }
      setPullDistance(Math.min(dy * 0.5, max));
    };

    const onTouchEnd = async () => {
      if (!pulling.current) return;
      pulling.current = false;
      const passed = pullDistance >= threshold;
      if (passed) {
        setRefreshing(true);
        setPullDistance(threshold);
        try {
          await onRefreshRef.current();
        } catch {
          /* ignore */
        }
        setRefreshing(false);
      }
      setPullDistance(0);
    };

    window.addEventListener("touchstart", onTouchStart, { passive: true });
    window.addEventListener("touchmove", onTouchMove, { passive: true });
    window.addEventListener("touchend", onTouchEnd, { passive: true });
    return () => {
      window.removeEventListener("touchstart", onTouchStart);
      window.removeEventListener("touchmove", onTouchMove);
      window.removeEventListener("touchend", onTouchEnd);
    };
  }, [refreshing, pullDistance, threshold, max]);

  return { pullDistance, refreshing };
}