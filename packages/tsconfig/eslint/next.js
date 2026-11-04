import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

/** Shared ESLint flat config for the Next.js apps. */
const config = [
  ...nextVitals,
  ...nextTs,
  {
    ignores: [".next/**", "out/**", "coverage/**", "next-env.d.ts"],
  },
];

export default config;
