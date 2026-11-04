import js from "@eslint/js";
import tseslint from "typescript-eslint";

/** Shared ESLint flat config for React library packages. */
const config = tseslint.config(js.configs.recommended, ...tseslint.configs.recommended, {
  ignores: ["dist/**", "coverage/**"],
});

export default config;
