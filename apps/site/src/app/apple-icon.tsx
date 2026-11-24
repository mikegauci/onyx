import { ImageResponse } from "next/og";

import { HandoffMark } from "@/components/handoff-mark";

export const size = { width: 180, height: 180 };
export const contentType = "image/png";

/** Home-screen version of the Onyx Studio favicon. */
export default function AppleIcon() {
  return new ImageResponse(
    <div
      style={{
        width: "100%",
        height: "100%",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "#151210",
      }}
    >
      <HandoffMark width={112} height={112} />
    </div>,
    size,
  );
}
