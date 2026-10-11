import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';

export default defineConfig({
  site: 'https://maioio.github.io',
  base: '/genesis-architect',
  trailingSlash: 'always',
  integrations: [
    starlight({
      title: 'Genesis Architect',
      favicon: '/favicon.svg',
      head: [
        { tag: 'meta', attrs: { property: 'og:image', content: 'https://maioio.github.io/genesis-architect/social-card.png' } },
        { tag: 'meta', attrs: { name: 'twitter:card', content: 'summary_large_image' } },
        // Scrollable code blocks must be keyboard reachable (axe: scrollable-region-focusable).
        { tag: 'script', content: "document.addEventListener('DOMContentLoaded',()=>document.querySelectorAll('.expressive-code pre').forEach(p=>{if(p.scrollWidth>p.clientWidth)p.setAttribute('tabindex','0')}))" },
      ],
      description: 'Research before you build. Understand before you change.',
      social: [{ icon: 'github', label: 'GitHub', href: 'https://github.com/maioio/genesis-architect' }],
      editLink: { baseUrl: 'https://github.com/maioio/genesis-architect/edit/main/site/' },
      customCss: ['./src/styles/theme.css'],
      sidebar: [
        { label: 'Start', items: ['getting-started', 'new-projects', 'existing-projects'] },
        { label: 'How it works', items: ['research-and-evidence', 'architecture-analysis', 'decision-engine', 'approval-model'] },
        { label: 'Reference', items: ['commands', 'mcp', 'agent-integrations', 'configuration', 'security', 'troubleshooting'] },
        { label: 'Project', items: ['architecture', 'limitations', 'contributing'] },
      ],
    }),
  ],
});
