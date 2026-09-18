// Fails if sv.json and en.json do not have exactly the same key set (spec 10, AT-10-2).
import { readFileSync } from "node:fs";

const flatten = (obj, prefix = "") =>
  Object.entries(obj).flatMap(([k, v]) =>
    typeof v === "object" && v !== null ? flatten(v, `${prefix}${k}.`) : [`${prefix}${k}`],
  );

const load = (locale) =>
  new Set(flatten(JSON.parse(readFileSync(`messages/${locale}.json`, "utf8"))));
const sv = load("sv");
const en = load("en");
const onlySv = [...sv].filter((k) => !en.has(k));
const onlyEn = [...en].filter((k) => !sv.has(k));
if (onlySv.length || onlyEn.length) {
  console.error("i18n key mismatch", { onlySv, onlyEn });
  process.exit(1);
}
console.log(`i18n ok: ${sv.size} keys in sv and en`);
