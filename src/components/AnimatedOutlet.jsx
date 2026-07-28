import { AnimatePresence, motion } from "framer-motion";
import { useOutlet, useLocation, useNavigationType } from "react-router-dom";

/**
 * Animated route outlet: slide-left on forward navigation,
 * slide-right on back (POP). The layout chrome stays persistent.
 */
export default function AnimatedOutlet() {
  const outlet = useOutlet();
  const location = useLocation();
  const navType = useNavigationType();
  const isBack = navType === "POP";
  const offset = 40;

  return (
    <AnimatePresence mode="wait" initial={false}>
      <motion.div
        key={location.pathname}
        initial={{ opacity: 0, x: isBack ? -offset : offset }}
        animate={{ opacity: 1, x: 0 }}
        exit={{ opacity: 0, x: isBack ? offset : -offset }}
        transition={{ duration: 0.22, ease: "easeOut" }}
      >
        {outlet}
      </motion.div>
    </AnimatePresence>
  );
}