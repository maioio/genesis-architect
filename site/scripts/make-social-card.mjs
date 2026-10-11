// Renders public/social-card.png (1200x630) from the facts file. Original artwork, no volatile counts.
import sharp from 'sharp';
import { readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const facts = JSON.parse(readFileSync(new URL('../../data/public-product-facts.json', import.meta.url), 'utf8'));
const version = facts.version ?? facts.product?.version ?? '';
const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630">
<rect width="1200" height="630" fill="#0b1020"/>
<g stroke="#1c2a4d" stroke-width="2" fill="none"><path d="M760 610 L900 540 L1010 570 L1200 440"/><path d="M880 630 L1040 520 L1200 560"/></g>
<g fill="#6ea8ff"><circle cx="900" cy="540" r="7"/><circle cx="1010" cy="570" r="7"/><circle cx="1040" cy="520" r="7"/></g>
<path d="M96 150 62 222h15l6.8-16.2h24.4L115 222h15L96 150Zm0 28.5 8 19.5H88l8-19.5Z" fill="#6ea8ff"/>
<text x="150" y="214" font-family="Segoe UI, Arial, sans-serif" font-size="44" font-weight="700" fill="#e8eeff">Genesis Architect</text>
<text x="60" y="340" font-family="Segoe UI, Arial, sans-serif" font-size="68" font-weight="700" fill="#ffffff">Evidence-first architecture</text>
<text x="60" y="420" font-family="Segoe UI, Arial, sans-serif" font-size="68" font-weight="700" fill="#ffffff">for real software.</text>
<text x="62" y="500" font-family="Segoe UI, Arial, sans-serif" font-size="30" fill="#9fb2d9">Research before you build. Understand before you change.</text>
<text x="62" y="580" font-family="Segoe UI, Arial, sans-serif" font-size="24" fill="#6ea8ff">maioio.github.io/genesis-architect${version ? '  ·  v' + version : ''}</text>
</svg>`;
const out = fileURLToPath(new URL('../public/social-card.png', import.meta.url));
writeFileSync(out, await sharp(Buffer.from(svg)).png().toBuffer());
console.log('wrote', out);
