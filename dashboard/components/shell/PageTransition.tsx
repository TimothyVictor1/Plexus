"use client";

import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

/** The same easing and the same manners as the landing page, so moving between the two does
 *  not feel like moving between two products. A screen rises a little as it arrives and the
 *  one it replaces is simply gone: a leaving animation would hold the old numbers on screen
 *  while the new ones are already true. */
const EASE = [0.22, 1, 0.36, 1] as const;

export default function PageTransition({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const reduced = useReducedMotion();

  if (reduced) return <>{children}</>;

  return (
    <AnimatePresence mode="wait" initial={false}>
      <motion.div
        key={pathname}
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.32, ease: EASE }}
        style={{ display: "flex", flexDirection: "column", flexGrow: 1, minHeight: 0 }}
      >
        {children}
      </motion.div>
    </AnimatePresence>
  );
}
