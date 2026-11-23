import { ImageResponse } from "next/og";

export const size = { width: 180, height: 180 };
export const contentType = "image/png";

/** Home-screen icon: the Onyx diamond on the dark canvas, matching icon.svg. */
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
      <div
        style={{
          width: 74,
          height: 74,
          borderRadius: 14,
          background: "#f08a3c",
          transform: "rotate(45deg)",
        }}
      />
    </div>,
    size,
  );
}
