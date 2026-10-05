"use client";

import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useEffect, useRef, useState } from "react";

/** The one easing every entrance on this page shares. */
const EASE = [0.22, 1, 0.36, 1] as const;

const VIDEO_SRC =
  "https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260809_012548_ef22562c-c0ae-4816-ad9d-f8922af4e6a7.mp4";

/** Where "Try Now" and "Sign in" lead: the console's front page. */
const APP_HREF = "/en";

const NAV = [
  { label: "Home", href: "/", active: true },
  { label: "Platform", href: "/", active: false },
  { label: "Shadow Company", href: "/", active: false },
  { label: "Contact", href: "/", active: false },
];

const INTEGRATIONS = ["fa-google", "fa-slack", "fa-hubspot"];
const LIFT = [-2, -4, -2];

type Stat = { icon: string; target: number; suffix: string; label: string };

const STATS: Stat[] = [
  { icon: "<", target: 1, suffix: " Layer", label: "Across Every Tool" },
  { icon: "%", target: 100, suffix: "%", label: "Data Kept In Europe" },
  { icon: "*", target: 24, suffix: "/7", label: "Shadow Workforce" },
  { icon: "#", target: 3, suffix: "", label: "Core Modules" },
];

/** The shared entrance: up out of a blur, once, on load. */
function reveal(delay: number, reduced: boolean) {
  if (reduced) return {};
  return {
    initial: { opacity: 0, y: 22, scale: 0.98, filter: "blur(6px)" },
    animate: { opacity: 1, y: 0, scale: 1, filter: "blur(0px)" },
    transition: { duration: 0.85, ease: EASE, delay },
  };
}

/** Counts up once the footer is actually on screen, then never again. */
function useCountUp(target: number, index: number, reduced: boolean) {
  const [value, setValue] = useState(reduced ? target : 0);
  const ref = useRef<HTMLDivElement>(null);
  const done = useRef(false);

  useEffect(() => {
    if (reduced || done.current) return;
    const node = ref.current;
    if (!node) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (!entries[0]?.isIntersecting || done.current) return;
        done.current = true;
        observer.disconnect();

        const duration = 1500 + index * 80;
        const startAfter = 480 + index * 90;
        let frame = 0;
        const begin = window.setTimeout(() => {
          const started = performance.now();
          const step = (now: number) => {
            const t = Math.min((now - started) / duration, 1);
            const eased = 1 - Math.pow(1 - t, 3); // easeOutCubic
            setValue(Math.round(target * eased));
            if (t < 1) frame = requestAnimationFrame(step);
          };
          frame = requestAnimationFrame(step);
        }, startAfter);

        return () => {
          window.clearTimeout(begin);
          cancelAnimationFrame(frame);
        };
      },
      { threshold: 0.25 },
    );

    observer.observe(node);
    return () => observer.disconnect();
  }, [target, index, reduced]);

  return { ref, value };
}

function StatBlock({ stat, index, reduced }: { stat: Stat; index: number; reduced: boolean }) {
  const { ref, value } = useCountUp(stat.target, index, reduced);
  return (
    <motion.div className="stat" ref={ref} {...reveal(0.5 + index * 0.08, reduced)}>
      <div className="stat-icon" aria-hidden="true">
        {stat.icon}
      </div>
      <div className="stat-value">
        {value}
        {stat.suffix}
      </div>
      <div className="stat-label">{stat.label}</div>
    </motion.div>
  );
}

/** The brand mark, until a real one is dropped in at public/landing/logo.webp.
 *
 *  The file is probed rather than rendered-and-caught: an <img> that 404s during the server
 *  render has already failed by the time React hydrates, so its onError never fires and the
 *  browser's broken-image icon stays on the page. Probing starts from the drawn mark and
 *  swaps only on success, so there is never a broken image to see.
 */
function LogoMark() {
  const [found, setFound] = useState(false);

  useEffect(() => {
    const probe = new Image();
    probe.onload = () => setFound(true);
    probe.src = "/landing/logo.webp";
  }, []);

  if (!found) {
    return (
      <svg viewBox="0 0 24 24" role="img" aria-label="Plexus">
        <circle cx="12" cy="12" r="3.2" fill="#000" />
        <circle cx="12" cy="3.4" r="1.9" fill="#000" />
        <circle cx="12" cy="20.6" r="1.9" fill="#000" />
        <circle cx="3.4" cy="12" r="1.9" fill="#000" />
        <circle cx="20.6" cy="12" r="1.9" fill="#000" />
        <g stroke="#000" strokeWidth="1.1">
          <line x1="12" y1="5.3" x2="12" y2="8.8" />
          <line x1="12" y1="15.2" x2="12" y2="18.7" />
          <line x1="5.3" y1="12" x2="8.8" y2="12" />
          <line x1="15.2" y1="12" x2="18.7" y2="12" />
        </g>
      </svg>
    );
  }
  return (
    // next/image is not used here because the file is optional and probed above.
    // eslint-disable-next-line @next/next/no-img-element
    <img src="/landing/logo.webp" alt="" width={52} height={52} />
  );
}

export default function Landing() {
  const reduced = useReducedMotion() ?? false;
  const [menuOpen, setMenuOpen] = useState(false);

  // Escape closes it, a wider viewport makes it irrelevant, and the body must not scroll under it.
  useEffect(() => {
    if (!menuOpen) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setMenuOpen(false);
    const onResize = () => window.innerWidth > 720 && setMenuOpen(false);
    document.body.classList.add("menu-open");
    window.addEventListener("keydown", onKey);
    window.addEventListener("resize", onResize);
    return () => {
      document.body.classList.remove("menu-open");
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("resize", onResize);
    };
  }, [menuOpen]);

  return (
    <>
      <div className="bg">
        <video className="bg-video" autoPlay muted loop playsInline>
          <source src={VIDEO_SRC} type="video/mp4" />
        </video>
      </div>

      <div className="page">
        <motion.header
          className="site-header"
          initial={reduced ? false : { opacity: 0, y: -18 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, ease: EASE }}
        >
          <motion.a className="logo" href="/" aria-label="Plexus" whileHover={{ scale: 1.04 }}>
            <LogoMark />
          </motion.a>

          <nav className="nav">
            {NAV.map((item) => (
              <motion.a
                key={item.label}
                href={item.href}
                className={item.active ? "active" : undefined}
                initial={{ opacity: item.active ? 1 : 0.5 }}
                whileHover={{ opacity: item.active ? 1 : 0.75 }}
              >
                {item.label}
              </motion.a>
            ))}
          </nav>

          <motion.a
            className="sign-in"
            href={APP_HREF}
            whileHover={{ y: -1, backgroundColor: "#323234", color: "#ffffff" }}
          >
            Sign in
          </motion.a>

          <motion.button
            className="burger"
            type="button"
            aria-label="Menu"
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen((open) => !open)}
            animate={{ backgroundColor: menuOpen ? "#ffffff" : "#28282a" }}
          >
            <span className="bars" aria-hidden="true">
              <motion.span
                className="bar"
                animate={
                  menuOpen
                    ? { y: 6.5, rotate: 45, backgroundColor: "#000" }
                    : { y: 0, rotate: 0, backgroundColor: "#fff" }
                }
              />
              <motion.span className="bar" animate={{ opacity: menuOpen ? 0 : 1 }} />
              <motion.span
                className="bar"
                animate={
                  menuOpen
                    ? { y: -6.5, rotate: -45, backgroundColor: "#000" }
                    : { y: 0, rotate: 0, backgroundColor: "#fff" }
                }
              />
            </span>
          </motion.button>
        </motion.header>

        <div className="hero">
          <motion.div className="trust" {...reveal(0.05, reduced)}>
            {INTEGRATIONS.map((icon, i) => (
              <motion.div
                key={icon}
                className={`avatar a${i + 1}`}
                whileHover={{ y: LIFT[i], transition: { duration: 0.35, ease: EASE } }}
              >
                <span>
                  <i className={`fa-brands ${icon}`} aria-hidden="true" />
                </span>
              </motion.div>
            ))}
            <div className="trust-pill">Plugs into your existing tools</div>
          </motion.div>

          <h1 className="headline">
            {["The Nervous System", "For Your Company"].map((line, i) => (
              <motion.span
                key={line}
                initial={reduced ? false : { opacity: 0, y: 14 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.85, ease: EASE, delay: i === 0 ? 0.12 : 0.3 }}
              >
                {line}
              </motion.span>
            ))}
          </h1>

          <motion.p className="subhead" {...reveal(0.28, reduced)}>
            One AI layer that connects your existing tools, learns your company&apos;s context and
            keeps your data in Europe.
          </motion.p>

          <motion.a
            className="cta"
            href={APP_HREF}
            initial={reduced ? false : { opacity: 0, y: 22, scale: 0.98, filter: "blur(6px)" }}
            animate={
              reduced
                ? {}
                : {
                    opacity: 1,
                    y: 0,
                    scale: [0.98, 1.04, 1],
                    filter: "blur(0px)",
                    boxShadow: [
                      "0 0 0 1px rgba(255,255,255,0.15), 0 0 22px rgba(255,255,255,0.32), 0 0 44px rgba(255,255,255,0.12)",
                      "0 0 0 1px rgba(255,255,255,0.3), 0 0 34px rgba(255,255,255,0.5), 0 0 64px rgba(255,255,255,0.2)",
                      "0 0 0 1px rgba(255,255,255,0.15), 0 0 22px rgba(255,255,255,0.32), 0 0 44px rgba(255,255,255,0.12)",
                    ],
                  }
            }
            transition={{ duration: 0.85, ease: EASE, delay: 0.4 }}
            whileHover={{
              y: -2,
              scale: 1.02,
              boxShadow:
                "0 0 0 1px rgba(255,255,255,0.25), 0 0 32px rgba(255,255,255,0.45), 0 0 60px rgba(255,255,255,0.2)",
            }}
            style={{
              boxShadow:
                "0 0 0 1px rgba(255,255,255,0.15), 0 0 22px rgba(255,255,255,0.32), 0 0 44px rgba(255,255,255,0.12)",
            }}
          >
            Try Now
          </motion.a>
        </div>

        <div className="stats">
          {STATS.map((stat, i) => (
            <StatBlock key={stat.label} stat={stat} index={i} reduced={reduced} />
          ))}
        </div>
      </div>

      <AnimatePresence>
        {menuOpen && (
          <>
            <motion.button
              className="m-overlay"
              type="button"
              aria-label="Close menu"
              onClick={() => setMenuOpen(false)}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.28, ease: EASE }}
            />
            <motion.div
              className="m-menu"
              initial={{ opacity: 0, y: -12, scale: 0.96, x: "-50%" }}
              animate={{ opacity: 1, y: 0, scale: 1, x: "-50%" }}
              exit={{ opacity: 0, y: -12, scale: 0.96, x: "-50%" }}
              transition={{ duration: 0.38, ease: EASE }}
            >
              {NAV.map((item, i) => (
                <motion.a
                  key={item.label}
                  href={item.href}
                  className={item.active ? "active" : undefined}
                  onClick={() => setMenuOpen(false)}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.3, ease: EASE, delay: 0.06 + i * 0.05 }}
                >
                  {item.label}
                </motion.a>
              ))}
              <motion.a
                className="sign-in"
                href={APP_HREF}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3, ease: EASE, delay: 0.06 + NAV.length * 0.05 }}
              >
                Sign in
              </motion.a>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </>
  );
}
