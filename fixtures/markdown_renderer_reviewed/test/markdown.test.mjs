import test from 'node:test';
import assert from 'node:assert/strict';
import { renderMarkdown } from '../src/markdown.ts';

test('renders ordinary Markdown with raw HTML disabled', () => {
  const html = renderMarkdown('# Hello\n\n**world** <script>alert(1)</script>');
  assert.match(html, /<h1>Hello<\/h1>/);
  assert.match(html, /<strong>world<\/strong>/);
  assert.doesNotMatch(html, /<script>/);
});

test('rejects input above 100 KiB', () => {
  assert.throws(() => renderMarkdown('x'.repeat(102401)), /100 KiB/);
});
