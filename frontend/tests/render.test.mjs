import assert from 'node:assert/strict';
import test from 'node:test';
import React from 'react';
import { renderToString } from 'react-dom/server';
import { createServer } from 'vite';

test('initial React output identifies a demo and discloses unavailable connections', async () => {
  // Component rendering only: no browser or assertion of browser cookie/layout
  // behavior. Disable the dev WebSocket and file watcher; no listener is needed.
  const server = await createServer({
    server: { middlewareMode: true, ws: false, watch: null },
    appType: 'custom',
  });
  try {
    const { default: App } = await server.ssrLoadModule('/src/App.jsx');
    const html = renderToString(React.createElement(App));
    for (const text of [
      'DEMO PREVIEW', 'Invented data', 'Not connected to your account',
      'Portfolio overview', 'Capital allocation', 'No live connection',
      'Not a return calculation',
    ]) assert.ok(html.includes(text), `Missing preview disclosure: ${text}`);
    assert.ok(!html.includes('type="password"'));
    assert.ok(!html.includes('<form'));
  } finally {
    await server.close();
  }
});
