import config from "@onyx/tsconfig/eslint/react-library";

export default [...config, { ignores: ["src/schema.ts"] }];
