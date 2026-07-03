import nextVitals from "eslint-config-next/core-web-vitals";
import reactRefresh from "eslint-plugin-react-refresh";

const config = [
  { ignores: ["dist", ".next", "next-env.d.ts", "tsconfig.test.tsbuildinfo"] },
  ...nextVitals,
  {
    files: ["**/*.{ts,tsx}"],
    plugins: {
      "react-refresh": reactRefresh,
    },
    rules: {
      "no-undef": "off",
      "react-refresh/only-export-components": [
        "warn",
        { allowConstantExport: true },
      ],
    },
  },
];

export default config;
