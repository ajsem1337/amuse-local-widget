const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const html = fs.readFileSync(`${__dirname}/../index.html`, 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];

function element(text = '') {
  const classes = new Set();
  const attributes = {};
  return {
    textContent: text, hidden: false, scrollWidth: 400, parentElement: { clientWidth: 200 },
    style: { setProperty(k, v) { this[k] = v; }, removeProperty(k) { delete this[k]; } },
    classList: {
      add(...names) { names.forEach(n => classes.add(n)); },
      remove(...names) { names.forEach(n => classes.delete(n)); },
      toggle(n, on) { if (on) classes.add(n); else classes.delete(n); },
      contains(n) { return classes.has(n); },
    },
    setAttribute(k, v) { attributes[k] = v; },
    removeAttribute(k) { delete attributes[k]; },
    getAttribute(k) { return attributes[k]; },
    querySelector() { return this.track; },
  };
}
function setup(fetch) {
  const elements = Object.fromEntries(['widget', 'title', 'artist', 'status', 'cover', 'fallback',
    'progressRow', 'progressFill', 'elapsed', 'duration'].map(id => [id, element()]));
  elements.progressRow.track = element();
  const timers = [];
  const context = vm.createContext({
    document: { getElementById: id => elements[id] },
    window: { addEventListener() {} }, requestAnimationFrame: fn => fn(),
    setTimeout: (fn, ms) => { timers.push({ fn, ms }); return timers.length; },
    clearTimeout() {}, AbortController, fetch,
  });
  vm.runInContext(script, context);
  return { context, elements, timers };
}
const settle = () => new Promise(resolve => setImmediate(resolve));

test('real progress, paused playback, and stopped state', async () => {
  let data = { title: 'Track', artist: 'Artist', status: 'Playing', position: 60, duration: 240 };
  const { context, elements } = setup(async () => ({ ok: true, json: async () => data }));
  await settle();
  assert.equal(elements.progressFill.style.width, '25%');
  assert.equal(elements.elapsed.textContent, '1:00');
  assert.equal(elements.status.textContent, 'Now playing');
  data.status = 'Paused';
  await vm.runInContext('update()', context);
  assert.equal(elements.widget.classList.contains('paused'), true);
  assert.equal(elements.progressRow.hidden, false);
  assert.equal(elements.progressFill.style.width, '25%');
  data.status = 'Stopped';
  await vm.runInContext('update()', context);
  assert.equal(elements.status.textContent, 'Stopped');
  assert.equal(elements.progressRow.hidden, true);
});

test('null timing is indeterminate and long tracks remain seconds', async () => {
  const { context, elements } = setup(async () => ({ ok: true, json: async () =>
    ({ title: 'Live', status: 'Playing', position: null, duration: null }) }));
  await settle();
  assert.equal(elements.progressRow.classList.contains('indeterminate'), true);
  assert.equal(elements.progressRow.track.getAttribute('aria-valuenow'), undefined);
  assert.equal(vm.runInContext('getPlaybackTimes({position: 7200, duration: 18000}).total', context), 18000);
  assert.equal(vm.runInContext('formatTime(18000)', context), '5:00:00');
});

test('slow request schedules no second poll until completion', async () => {
  let finish;
  const { timers } = setup(() => new Promise(resolve => { finish = resolve; }));
  assert.equal(timers.filter(t => t.ms === 1000).length, 0);
  finish({ ok: true, json: async () => ({}) });
  await settle();
  assert.equal(timers.filter(t => t.ms === 1000).length, 1);
});

test('HTTP failure clears stale state and recovers', async () => {
  let ok = false;
  const { context, elements } = setup(async () => ({ ok, status: 503, json: async () =>
    ({ title: 'Recovered', status: 'Playing', position: 0, duration: 60 }) }));
  await settle();
  assert.equal(elements.status.textContent, 'Offline');
  assert.equal(elements.progressRow.hidden, true);
  ok = true;
  await vm.runInContext('update()', context);
  assert.equal(elements.title.textContent, 'Recovered');
  assert.equal(elements.widget.classList.contains('empty'), false);
});

test('unchanged artwork and text keep their state across polls', async () => {
  const { context, elements } = setup(async () => ({ ok: true, json: async () =>
    ({ title: 'Long title', status: 'Playing', artUrl: '/cover?id=one' }) }));
  await settle();
  let changes = 0;
  Object.defineProperty(elements.cover, 'src', { set() { changes++; } });
  await vm.runInContext('update()', context);
  assert.equal(changes, 0);
  assert.equal(elements.title.classList.contains('scroll'), true);
  assert.equal(elements.title.style['--scroll-distance'], '-200px');
});
