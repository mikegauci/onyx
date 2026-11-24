import { ImageResponse } from "next/og";

import { HandoffMark } from "@/components/handoff-mark";
import { site } from "@/content/site";

export const alt = `${site.name}: ${site.tagline}`;
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default function OpengraphImage() {
  return new ImageResponse(
    <div
      style={{
        width: "100%",
        height: "100%",
        display: "flex",
        flexDirection: "column",
        justifyContent: "space-between",
        padding: 80,
        background: "radial-gradient(circle at 80% 0%, #5a2c12 0%, #120f0d 55%)",
        color: "#f4f2f0",
        fontFamily: "sans-serif",
      }}
    >
      <div
        style={{ display: "flex", alignItems: "center", gap: 18, fontSize: 36, fontWeight: 600 }}
      >
        <HandoffMark width={36} height={36} />
        {site.name}
      </div>
      <div style={{ fontSize: 68, fontWeight: 600, lineHeight: 1.1, maxWidth: 980 }}>
        {site.tagline}
      </div>
      <div style={{ fontSize: 28, color: "#b9b2ac" }}>onyx.mt</div>
    </div>,
    size,
  );
}
