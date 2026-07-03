import js from "@eslint/js";
import nextVitals from "eslint-config-next/core-web-vitals";
import reactRefresh from "eslint-plugin-react-refresh";

export default [
  { ignores: ["dist", ".next", "next-env.d.ts", "tsconfig.test.tsbuildinfo"] },
  js.configs.recommended,
  ...nextVitals,
  {
    files: ["**/*.{js,mjs,cjs,ts,tsx}"],
    rules: {
      "import/no-anonymous-default-export": "off",
    },
  },
  {
    files: ["**/*.{ts,tsx}"],
    plugins: {
      "react-refresh": reactRefresh,
    },
    rules: {
      "no-undef": "off",
      "no-unused-vars": "off",
      "import/no-anonymous-default-export": "off",
      "@next/next/no-img-element": "off",
      "react-hooks/refs": "off",
      "react-hooks/set-state-in-effect": "off",
      "react-hooks/static-components": "off",
      "@typescript-eslint/no-explicit-any": 0,
      "@typescript-eslint/no-unused-vars": "off",
      "react-refresh/only-export-components": [
        "warn",
        { allowConstantExport: true },
      ],
    },
  },
];
