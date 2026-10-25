// SPDX-License-Identifier: BSD-3-Clause
// Execute the actual TSX with controlled hooks, RPC completion and timers (same approach as FSR4 Injector).
const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '..'), ts = require(path.join(root, 'node_modules/typescript'));
const settle = async () => { for (let i = 0; i < 24; i++) await Promise.resolve(); };

function harness(runningApp) {
  const slots = [], effects = new Map(), pending = [], calls = [], timers = [];
  let cursor = 0;
  const same = (a, b) => a && b && a.length === b.length && a.every((v, i) => v === b[i]);
  const hooks = {
    useState(value) { const i = cursor++; if (!(i in slots)) slots[i] = typeof value === 'function' ? value() : value;
      return [slots[i], v => { slots[i] = typeof v === 'function' ? v(slots[i]) : v; }]; },
    useCallback(fn, deps) { const i = cursor++; if (!slots[i] || !same(slots[i].deps, deps)) slots[i] = { fn, deps }; return slots[i].fn; },
    useEffect(fn, deps) { const i = cursor++, old = effects.get(i); if (!old || !same(old.deps, deps)) pending.push(() => {
      old?.cleanup?.(); effects.set(i, { deps, cleanup: fn() });
    }); },
  };
  const el = (type, props) => (typeof type === 'function' && !['Note'].includes(type.name) ? type(props) : { type, props });
  const jsx = { jsx: el, jsxs: el, Fragment: 'Fragment' };
  const callable = name => (...args) => new Promise((resolve, reject) => calls.push({ name, args, resolve, reject, settled: false }));
  const ui = new Proxy({ Router: { get MainRunningApp() { return runningApp; } } }, { get: (o, k) => (k in o ? o[k] : k) });
  const source = fs.readFileSync(path.join(root, 'src', 'index.tsx'), 'utf8') + '\nexport { Content };';
  const output = ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX } }).outputText;
  const mod = { exports: {} };
  vm.runInNewContext(output, {
    module: mod, exports: mod.exports, console,
    setTimeout: (fn, ms) => { const t = { fn, ms, done: false }; timers.push(t); return t; },
    clearTimeout: t => { if (t) t.done = true; }, setInterval: () => 1, clearInterval() {},
    require(name) {
      if (name === 'react') return hooks;
      if (name === 'react/jsx-runtime') return jsx;
      if (name === '@decky/api') return { callable, definePlugin: fn => fn };
      if (name === '@decky/ui') return ui;
      throw Error(name);
    },
  });
  const render = () => { cursor = 0; const tree = mod.exports.Content({}); pending.splice(0).forEach(fn => fn()); return tree; };
  return {
    render, calls, timers,
    respond(name, value) {
      const call = calls.find(c => c.name === name && !c.settled); assert.ok(call, `pending ${name}`);
      call.settled = true; call.resolve(value); return call;
    },
    fire() { timers.filter(t => !t.done).forEach(t => { t.done = true; t.fn(); }); },
  };
}

function all(node, out = []) {
  if (Array.isArray(node)) node.forEach(n => all(n, out));
  else if (node && typeof node === 'object') { out.push(node); all(node.props?.children, out); }
  return out;
}
const find = (tree, type, label) => all(tree).find(n => n.type === type && (label === undefined || n.props.label === label));

const base = {
  version: '0.1.0', pinned: '2.0.0', lsfg: { ok: true, text: '', version: '2.0.0' }, managed: true,
  managed_version: '2.0.0', busy: '', error: '', lossless_scaling: { installed: true, dll: '/ls/lsfg-vk.dll' },
  rivals: [], config_error: '', games: [], game: null,
};
const game = (settings = null, attached = null) => ({ ...base, game: {
  appid: 1809540, name: 'Nine Sols', ids: ['1809540'], running: true, settings, attached } });

(async () => {
  // A running game without a profile: off; picking 2x saves the defaults for its ids at once.
  {
    const h = harness({ appid: '1809540', display_name: 'Nine Sols' });
    h.render();
    assert.deepEqual(h.calls[0].args, [1809540, 'Nine Sols']);
    h.respond('get_state', game());
    await settle();
    let tree = h.render();
    const fg = find(tree, 'DropdownItem', 'Frame generation');
    assert.equal(fg.props.selectedOption, 1);
    assert.equal(find(tree, 'SliderField'), undefined, 'no tuning while off');
    fg.props.onChange({ data: 2 });
    tree = h.render();
    assert.equal(find(tree, 'DropdownItem', 'Frame generation').props.selectedOption, 2, 'shown before the backend answers');
    h.fire();
    const saved = h.calls.find(c => c.name === 'set_profile');
    assert.deepEqual(saved.args, [['1809540'], 'Nine Sols', 2, 1, true, 1809540]);
    h.respond('set_profile', game({ name: 'Nine Sols', ids: ['1809540'], multiplier: 2, flow_scale: 1, performance_mode: true }));
    await settle();
    tree = h.render();
    assert.match(find(tree, 'Field', 'Status').props.description, /Restart the game/);
  }

  // Slider steps are saved once, after the user stops moving it; attached status names how lsfg-vk found the game.
  {
    const h = harness({ appid: 1809540, display_name: 'Nine Sols' });
    h.render();
    const on = { name: 'Nine Sols', ids: ['1809540'], multiplier: 3, flow_scale: 1, performance_mode: true };
    h.respond('get_state', game(on, { profile: 'Nine Sols', via: 'Steam App ID' }));
    await settle();
    let tree = h.render();
    assert.match(find(tree, 'Field', 'Status').props.description, /^On: .*Steam App ID/);
    for (const v of [95, 90, 85]) { find(h.render(), 'SliderField').props.onChange(v); }
    assert.equal(find(h.render(), 'SliderField').props.value, 85);
    h.fire();
    const saves = h.calls.filter(c => c.name === 'set_profile');
    assert.equal(saves.length, 1);
    assert.deepEqual(saves[0].args, [['1809540'], 'Nine Sols', 3, 0.85, true, 1809540]);
  }

  // Games list: every game can be set up before it starts, in the backend's order; the running game is not
  // listed twice; a game set up before keeps its own tuning when only the multiplier changes.
  {
    const h = harness({ appid: 1809540, display_name: 'Nine Sols' });
    h.render();
    const tuned = { name: 'Hades', ids: ['1145360'], multiplier: 3, flow_scale: 0.7, performance_mode: false };
    const listed = { ...game(), games: [
      { appid: 2147483649, name: 'Shortcut', ids: ['2147483649', 'Game.exe'], settings: null },
      { appid: 1145360, name: 'Hades', ids: ['1145360'], settings: tuned },
      { appid: 1809540, name: 'Nine Sols', ids: ['1809540'], settings: null },
      { appid: 3, name: 'Ärger 10', ids: ['3'], settings: null },
      { appid: 4, name: 'Ärger 9', ids: ['4'], settings: null },
      { appid: 0, name: 'genshin', ids: ['GenshinImpact.exe'], settings: { ...tuned, name: 'genshin', ids: ['GenshinImpact.exe'] } }] };
    h.respond('get_state', listed);
    await settle();
    let tree = h.render();
    const rows = all(tree).filter(n => n.type === 'DropdownItem').map(n => n.props.label);
    assert.deepEqual(rows, ['Frame generation', 'Ärger 9', 'Ärger 10', 'genshin', 'Hades', 'Shortcut'], 'alphabetical, running game on top only');
    assert.equal(find(tree, 'DropdownItem', 'Shortcut').props.selectedOption, 1, 'never set up shows Off');
    find(tree, 'DropdownItem', 'Shortcut').props.onChange({ data: 2 });
    h.fire();
    assert.deepEqual(h.calls.find(c => c.name === 'set_profile').args, [['2147483649', 'Game.exe'], 'Shortcut', 2, 1, true, 1809540]);
    h.respond('set_profile', listed);
    await settle();
    find(h.render(), 'DropdownItem', 'Hades').props.onChange({ data: 1 });
    h.fire();
    assert.deepEqual(h.calls.filter(c => c.name === 'set_profile')[1].args, [['1145360'], 'Hades', 1, 0.7, false, 1809540]);
  }

  // No game: a hint, the games list, and the install button when lsfg-vk is missing.
  {
    const h = harness(undefined);
    h.render();
    assert.deepEqual(h.calls[0].args, [0, '']);
    h.respond('get_state', { ...base, lsfg: null, managed: false, lossless_scaling: { installed: true, dll: '' },
      games: [{ appid: 0, name: 'Genshin', ids: ['GenshinImpact.exe'], settings: null }] });
    await settle();
    const tree = h.render();
    assert.ok(find(tree, 'Field', 'No game running'));
    assert.equal(find(tree, 'DropdownItem', 'Genshin').props.disabled, true, 'nothing to change until lsfg-vk is installed');
    const install = all(tree).find(n => n.type === 'ButtonItem');
    assert.equal(install.props.children, 'Install lsfg-vk 2.0.0');
    assert.ok(all(tree).some(n => n.type?.name === 'Note' && String(n.props.children).includes('Betas')), 'wrong Steam branch is explained');
    install.props.onClick();
    assert.ok(h.calls.some(c => c.name === 'install_lsfg'));
  }
  console.log('frontend panel: ok');
})().catch(e => { console.error(e); process.exit(1); });
