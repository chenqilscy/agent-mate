// Markdown pipeline: marked → highlight.js → DOMPurify.
//
// Security hard-line (spec 8, #1): LLM output MUST pass through DOMPurify before
// it can reach dangerouslySetInnerHTML. Never bypass this for assistant content.

import { marked } from 'marked'
import DOMPurify from 'dompurify'
// `lib/common` bundles ~35 popular languages instead of all 190+ — much smaller.
// Token colors are theme-aware CSS in app.css (not an imported light-only theme),
// so code blocks read correctly in both light and dark mode.
import hljs from 'highlight.js/lib/common'

marked.setOptions({
  gfm: true,
  breaks: false,
})

// Syntax-highlight fenced code blocks via a marked extension.
marked.use({
  renderer: {
    code({ text, lang }: { text: string; lang?: string }) {
      let highlighted: string
      if (lang && hljs.getLanguage(lang)) {
        highlighted = hljs.highlight(text, { language: lang }).value
      } else {
        highlighted = hljs.highlightAuto(text).value
      }
      return `<pre><code class="hljs language-${lang ?? ''}">${highlighted}</code></pre>`
    },
  },
})

// Open links in a new tab and keep them safe.
DOMPurify.addHook('afterSanitizeAttributes', (node) => {
  if (node.tagName === 'A') {
    node.setAttribute('target', '_blank')
    node.setAttribute('rel', 'noopener noreferrer')
  }
})

export function renderMarkdown(md: string): string {
  const raw = marked.parse(md, { async: false }) as string
  return DOMPurify.sanitize(raw, {
    ADD_ATTR: ['target', 'rel'],
  })
}
