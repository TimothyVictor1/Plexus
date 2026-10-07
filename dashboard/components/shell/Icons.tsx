import type { SVGProps } from "react";

const base = {
  width: 20, height: 20, viewBox: "0 0 24 24", fill: "none",
  stroke: "currentColor", strokeWidth: 1.8,
  strokeLinecap: "round" as const, strokeLinejoin: "round" as const,
};

export const PlexusMark = (p: SVGProps<SVGSVGElement>) => (
  // Lavender, the one hue the product allows itself, and the colour of the landing video.
  <svg width="30" height="30" viewBox="0 0 30 30" fill="none" stroke="var(--hi)"
       strokeWidth="2.2" strokeLinecap="round" aria-hidden="true" {...p}>
    <circle cx="15" cy="15" r="3.2" /><circle cx="5" cy="7" r="2.2" />
    <circle cx="25" cy="7" r="2.2" /><circle cx="5" cy="23" r="2.2" />
    <circle cx="25" cy="23" r="2.2" />
    <path d="M7 8.5 12.3 13M23 8.5 17.7 13M7 21.5 12.3 17M23 21.5 17.7 17" />
  </svg>
);

export const PlusIcon = () => (
  <svg {...base} strokeWidth={2.4} aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg>
);
export const HomeIcon = () => (
  <svg {...base} aria-hidden="true"><path d="M4 11 12 4l8 7v8a1 1 0 0 1-1 1h-4v-6h-6v6H5a1 1 0 0 1-1-1z" /></svg>
);
export const AskIcon = () => (
  <svg {...base} aria-hidden="true"><path d="M5 5h14a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1h-8l-5 4v-4H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1z" /></svg>
);
export const WorkIcon = () => (
  <svg {...base} aria-hidden="true">
    <circle cx="6" cy="6" r="2.5" /><circle cx="18" cy="18" r="2.5" />
    <path d="M8.5 6H15a3 3 0 0 1 0 6H9a3 3 0 0 0 0 6h6.5" />
  </svg>
);
export const ReviewIcon = () => (
  <svg {...base} aria-hidden="true"><path d="M4 13h4l2 3h4l2-3h4M4 13l2.5-7h11l2.5 7v6H4z" /></svg>
);
export const ConnectIcon = () => (
  <svg {...base} aria-hidden="true"><path d="M9 3v4M15 3v4M7 7h10v4a5 5 0 0 1-10 0zM12 16v5" /></svg>
);
// Sliders, not a gear with rays: the old drawing was a circle with eight spokes, which is a
// sun, and sat in the rail next to the theme toggle looking exactly like it.
export const SettingsIcon = () => (
  <svg {...base} aria-hidden="true">
    <path d="M4 7h10M18 7h2M4 12h3M11 12h9M4 17h7M15 17h5" />
    <circle cx="16" cy="7" r="2" />
    <circle cx="9" cy="12" r="2" />
    <circle cx="13" cy="17" r="2" />
  </svg>
);
export const SlowIcon = () => (
  <svg {...base} aria-hidden="true"><path d="M4 19h16M7 16V11M12 16V6M17 16v-3" /></svg>
);
export const SearchIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#8A8A92"
       strokeWidth="2" strokeLinecap="round" aria-hidden="true">
    <circle cx="11" cy="11" r="6.5" /><path d="m20 20-4-4" />
  </svg>
);

export const TwinIcon = () => (
  <svg {...base} aria-hidden="true">
    <circle cx="12" cy="6" r="2.4" /><circle cx="5.5" cy="17" r="2.4" />
    <circle cx="18.5" cy="17" r="2.4" />
    <path d="M10.4 7.8 7 14.6M13.6 7.8 17 14.6M8 17.4h8" />
  </svg>
);

// The shadow workforce: someone doing the work, and the outline learning it from behind.
export const ShadowIcon = () => (
  <svg {...base} aria-hidden="true">
    <circle cx="9" cy="8" r="3" />
    <path d="M3.5 19a5.5 5.5 0 0 1 11 0" />
    <circle cx="16.5" cy="8.5" r="2.2" strokeDasharray="2 2" />
    <path d="M13.5 19a4.6 4.6 0 0 1 7 0" strokeDasharray="2 2" />
  </svg>
);
