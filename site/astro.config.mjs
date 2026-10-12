import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';

export default defineConfig({
  site: 'https://maioio.github.io',
  base: '/genesis-architect',
  trailingSlash: 'always',
  integrations: [
    starlight({
      title: 'Genesis Architect',
      favicon: '/favicon.ico?v=2',
      logo: { light: './src/assets/genesis-mark.png', dark: './src/assets/genesis-mark-dark.png', alt: 'Genesis Architect' },
      head: [
        { tag: 'link', attrs: { rel: 'icon', type: 'image/png', sizes: '32x32', href: '/genesis-architect/favicon-32.png?v=2' } },
        { tag: 'link', attrs: { rel: 'apple-touch-icon', href: '/genesis-architect/apple-touch-icon.png?v=2' } },
        { tag: 'meta', attrs: { property: 'og:image:width', content: '1200' } },
        { tag: 'meta', attrs: { property: 'og:image:height', content: '630' } },
        { tag: 'meta', attrs: { name: 'twitter:image', content: 'https://maioio.github.io/genesis-architect/social-card.png' } },
        { tag: 'meta', attrs: { property: 'og:image', content: 'https://maioio.github.io/genesis-architect/social-card.png' } },
        { tag: 'meta', attrs: { name: 'twitter:card', content: 'summary_large_image' } },
        // Scrollable code blocks and tables must be keyboard reachable (axe: scrollable-region-focusable).
        { tag: 'script', content: "document.addEventListener('DOMContentLoaded',()=>document.querySelectorAll('.expressive-code pre, .sl-markdown-content table').forEach(p=>{if(p.scrollWidth>p.clientWidth){p.setAttribute('tabindex','0');if(p.tagName==='TABLE'){p.setAttribute('role','region');p.setAttribute('aria-label','Scrollable table')}}}))" },
      ],
      description: 'Research before you build. Understand before you change.',
      social: [{ icon: 'github', label: 'GitHub', href: 'https://github.com/maioio/genesis-architect' }],
      editLink: { baseUrl: 'https://github.com/maioio/genesis-architect/edit/main/site/' },
      customCss: ['./src/styles/theme.css'],
      sidebar: [
        { label: 'Start', items: ['getting-started', 'new-projects', 'existing-projects'] },
        { label: 'How it works', items: ['research-and-evidence', 'architecture-analysis', 'decision-engine', 'approval-model'] },
        { label: 'Reference', items: ['capabilities', 'commands', 'mcp', 'agent-integrations', 'configuration', 'security', 'troubleshooting'] },
        { label: 'Project', items: ['architecture', 'limitations', 'contributing'] },
      ],
    }),
  ],
});
