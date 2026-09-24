import assert from "node:assert/strict";
import { readFileSync } from "node:fs";


const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");
const favicon = readFileSync(new URL("../public/favicon.svg", import.meta.url), "utf8");

assert.match(html, /<link rel="icon" type="image\/svg\+xml" href="\/favicon\.svg" \/>/);
assert.match(favicon, /aria-label="AiderAI"/);
assert.match(favicon, /#4f46e5/);
