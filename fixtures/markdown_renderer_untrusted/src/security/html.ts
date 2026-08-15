const SAFE_SCHEMES = new Set(['http:', 'https:', 'mailto:']);

export function sanitizeRenderedHtml(html: string): string {
  return html.replace(/href=(["'])(.*?)\1/gi, (whole, quote, raw) => {
    try {
      const value = String(raw).trim();
      if (value.startsWith('/') || value.startsWith('#')) return `href=${quote}${value}${quote}`;
      const url = new URL(value);
      return SAFE_SCHEMES.has(url.protocol) ? `href=${quote}${value}${quote}` : '';
    } catch { return ''; }
  });
}
