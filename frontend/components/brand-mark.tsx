"use client";

import Link from "next/link";

type Props = {
  compact?: boolean;
  href?: string;
};

export function BrandMark({ compact = false, href = "/" }: Props) {
  const content = (
    <div className={`flex items-center ${compact ? "gap-3" : "gap-4"}`}>
      <div className={`brand-emblem ${compact ? "h-11 w-11" : "h-14 w-14"}`} aria-hidden="true">
        <svg viewBox="0 0 64 64" className="h-full w-full" fill="none">
          <defs>
            <linearGradient id="brandCore" x1="10" y1="8" x2="54" y2="56" gradientUnits="userSpaceOnUse">
              <stop stopColor="#FFDFA5" />
              <stop offset="0.5" stopColor="#F08B44" />
              <stop offset="1" stopColor="#B5481D" />
            </linearGradient>
            <linearGradient id="brandShadow" x1="22" y1="18" x2="48" y2="48" gradientUnits="userSpaceOnUse">
              <stop stopColor="#102033" stopOpacity="0.1" />
              <stop offset="1" stopColor="#102033" stopOpacity="0.35" />
            </linearGradient>
          </defs>
          <path d="M12 20.5 31.8 9 52 20.5v23L31.8 55 12 43.5v-23Z" fill="url(#brandCore)" />
          <path d="M12 20.5 31.8 32 52 20.5" stroke="#FFF7EC" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
          <path d="M31.8 32V55" stroke="#FFF7EC" strokeWidth="2.5" strokeLinecap="round" />
          <path d="M22 26.5h19.5" stroke="#102033" strokeOpacity="0.18" strokeWidth="2.5" strokeLinecap="round" />
          <circle cx="45.5" cy="19" r="7.5" fill="#102033" />
          <path d="m43.5 19 1.4 1.4 3.6-3.8" stroke="#FFF7EC" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          <ellipse cx="32" cy="46" rx="17" ry="6.5" fill="url(#brandShadow)" />
        </svg>
      </div>
      <div>
        <p className={`brand-kicker ${compact ? "text-[0.62rem]" : ""}`}>Portal Comercial 3D</p>
        <p className={`${compact ? "text-xl" : "text-[1.7rem]"} brand-wordmark`}>EuAchei3D</p>
      </div>
    </div>
  );

  return href ? (
    <Link href={href} className="inline-flex items-center">
      {content}
    </Link>
  ) : (
    content
  );
}
