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
  // Arguments are copied out of the sandbox, whose objects have their own Object prototype.
  const callable = name => (...args) => new Promise((resolve, reject) =>
    calls.push({ name, args: JSON.parse(JSON.stringify(args)), resolve, reject, settled: false }));
  const steam = [];  // what the panel asked Steam to open, in order
  const Navigation = { CloseSideMenus: () => steam.push('close menus'), Navigate: p => steam.push(`navigate ${p}`) };
  const ui = new Proxy({ Router: { get MainRunningApp() { return runningApp; } }, Navigation },
    { get: (o, k) => (k in o ? o[k] : k) });
  // Steam app types: 1 game, 4 tool (Ubisoft Connect Services, Proton...); apps not listed have no overview.
  const appTypes = { 1145360: 1, 1809540: 1, 4099820: 4, 1493710: 4 };
  const appStore = { GetAppOverviewByAppID: id => (id in appTypes ? { app_type: appTypes[id] } : null) };
  const SteamClient = { URL: { ExecuteSteamURL: url => steam.push(`url ${url}`) } };
  const source = fs.readFileSync(path.join(root, 'src', 'index.tsx'), 'utf8') + '\nexport { Content };';
  const output = ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX } }).outputText;
  const mod = { exports: {} };
  vm.runInNewContext(output, {
    module: mod, exports: mod.exports, console, appStore, SteamClient,
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
    render, calls, timers, steam,
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
  rivals: [], config_error: '', allow_fp16: true, games: [], game: null,
};
const Q = { override_present_mode: true, preserve_swapchain_image_count: false };
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
    assert.deepEqual(saved.args, [['1809540'], 'Nine Sols', { multiplier: 2, flow_scale: 1, performance_mode: true, ...Q }, 1809540, 'Nine Sols']);
    h.respond('set_profile', game({ name: 'Nine Sols', ids: ['1809540'], multiplier: 2, flow_scale: 1, performance_mode: true, ...Q }));
    await settle();
    tree = h.render();
    assert.match(find(tree, 'Field', 'Status').props.description, /Restart the game/);
  }

  // Slider steps are saved once, after the user stops moving it; attached status names how lsfg-vk found the game.
  {
    const h = harness({ appid: 1809540, display_name: 'Nine Sols' });
    h.render();
    const on = { name: 'Nine Sols', ids: ['1809540'], multiplier: 3, flow_scale: 1, performance_mode: true, ...Q };
    h.respond('get_state', game(on, { profile: 'Nine Sols', via: 'Steam App ID' }));
    await settle();
    let tree = h.render();
    assert.match(find(tree, 'Field', 'Status').props.description, /^On: .*Steam App ID/);
    for (const v of [95, 90, 85]) { find(h.render(), 'SliderField').props.onChange(v); }
    assert.equal(find(h.render(), 'SliderField').props.value, 85);
    h.fire();
    const saves = h.calls.filter(c => c.name === 'set_profile');
    assert.equal(saves.length, 1);
    assert.deepEqual(saves[0].args, [['1809540'], 'Nine Sols', { multiplier: 3, flow_scale: 0.85, performance_mode: true, ...Q }, 1809540, 'Nine Sols']);
  }

  // Multipliers up to 8x; compatibility options are folded away and keep every other setting; FP16 is global.
  {
    const h = harness({ appid: 1809540, display_name: 'Nine Sols' });
    h.render();
    const on = { name: 'Nine Sols', ids: ['1809540'], multiplier: 2, flow_scale: 0.8, performance_mode: false, ...Q };
    h.respond('get_state', game(on, { profile: 'Nine Sols', via: 'Steam App ID' }));
    await settle();
    let tree = h.render();
    assert.deepEqual(Array.from(find(tree, 'DropdownItem', 'Frame generation').props.rgOptions, o => o.label),
      ['Off', '2×', '3×', '4×', '5×', '6×', '7×', '8×']);
    assert.equal(find(tree, 'ToggleField', 'Force V-Sync'), undefined, 'compatibility options start folded');
    all(tree).find(n => n.type === 'ButtonItem' && n.props.children === 'Compatibility options').props.onClick();
    tree = h.render();
    assert.equal(find(tree, 'ToggleField', 'Force V-Sync').props.checked, true);
    find(tree, 'ToggleField', "Keep the game's buffer count").props.onChange(true);
    h.fire();
    assert.deepEqual(h.calls.find(c => c.name === 'set_profile').args, [['1809540'], 'Nine Sols',
      { multiplier: 2, flow_scale: 0.8, performance_mode: false, override_present_mode: true,
        preserve_swapchain_image_count: true }, 1809540, 'Nine Sols'], 'only the changed key differs; no name or ids inside');
    find(h.render(), 'ToggleField', 'Half precision (FP16)').props.onChange(false);
    assert.deepEqual(h.calls.find(c => c.name === 'set_fp16').args, [false, 1809540, 'Nine Sols']);
  }

  // Games list: collapsed at first; expanded it is alphabetical without the running game. A switch turned on
  // prepares the game at 1× (the multiplier is chosen in the game), turned off it removes the game's profile.
  {
    const h = harness({ appid: 1809540, display_name: 'Nine Sols' });
    h.render();
    const tuned = { name: 'Hades', ids: ['1145360'], multiplier: 3, flow_scale: 0.7, performance_mode: false, ...Q };
    const listed = { ...game(), games: [
      { appid: 2147483649, name: 'Shortcut', ids: ['2147483649', 'Game.exe'], settings: null },
      { appid: 1145360, name: 'Hades', ids: ['1145360'], settings: tuned },
      { appid: 1809540, name: 'Nine Sols', ids: ['1809540'], settings: null },
      { appid: 3, name: 'Ärger 10', ids: ['3'], settings: null },
      { appid: 4, name: 'Ärger 9', ids: ['4'], settings: null },
      { appid: 4099820, name: 'Ubisoft Connect Services', ids: ['4099820'], settings: null },
      { appid: 0, name: 'genshin', ids: ['GenshinImpact.exe'], settings: { ...tuned, multiplier: 1, name: 'genshin', ids: ['GenshinImpact.exe'] } }] };
    h.respond('get_state', listed);
    await settle();
    let tree = h.render();
    const toggles = t => all(t).filter(n => n.type === 'ToggleField' && n.props.label !== 'Half precision (FP16)').map(n => n.props.label);
    const expand = all(tree).find(n => n.type === 'ButtonItem' && String(n.props.children).startsWith('Show games'));
    assert.equal(expand.props.children, 'Show games (2 on)');
    assert.deepEqual(toggles(tree), [], 'collapsed by default');
    expand.props.onClick();
    tree = h.render();
    assert.deepEqual(toggles(tree), ['Ärger 9', 'Ärger 10', 'genshin', 'Hades', 'Shortcut'],
      'alphabetical, running game on top only, Steam tools (Ubisoft Connect Services) left out');
    assert.equal(find(tree, 'ToggleField', 'Hades').props.description, '3× frame generation');
    assert.equal(find(tree, 'ToggleField', 'genshin').props.description, 'Ready');
    assert.equal(find(tree, 'ToggleField', 'Shortcut').props.checked, false);
    find(tree, 'ToggleField', 'Shortcut').props.onChange(true);
    assert.equal(find(h.render(), 'ToggleField', 'Shortcut').props.checked, true, 'shown before the backend answers');
    find(h.render(), 'ToggleField', 'Hades').props.onChange(false);
    h.fire();
    assert.deepEqual(h.calls.find(c => c.name === 'set_profile').args,
      [['2147483649', 'Game.exe'], 'Shortcut', { multiplier: 1, flow_scale: 1, performance_mode: true, ...Q }, 1809540, 'Nine Sols'], 'both switches saved, neither swallowed');
    assert.deepEqual(h.calls.find(c => c.name === 'remove_profile').args, [['1145360'], 1809540, 'Nine Sols']);
    assert.equal(find(h.render(), 'ToggleField', 'Hades').props.checked, false);
  }

  // No game: a hint, the games list, and the install button when lsfg-vk is missing.
  {
    const h = harness(undefined);
    h.render();
    assert.deepEqual(h.calls[0].args, [0, '']);
    h.respond('get_state', { ...base, lsfg: null, managed: false, lossless_scaling: { installed: true, dll: '' },
      games: [{ appid: 0, name: 'Genshin', ids: ['GenshinImpact.exe'], settings: null }] });
    await settle();
    let tree = h.render();
    assert.ok(find(tree, 'Field', 'No game running'));
    all(tree).find(n => n.type === 'ButtonItem' && String(n.props.children).startsWith('Show games')).props.onClick();
    tree = h.render();
    assert.equal(find(tree, 'ToggleField', 'Genshin').props.disabled, true, 'nothing to change until lsfg-vk is installed');
    const install = all(tree).find(n => n.type === 'ButtonItem');
    assert.equal(install.props.children, 'Install lsfg-vk 2.0.0');
    assert.ok(all(tree).some(n => n.type?.name === 'Note' && String(n.props.children).includes('Betas')), 'wrong Steam branch is explained');
    all(tree).find(n => n.type === 'ButtonItem' && n.props.children === 'Open Lossless Scaling in the library').props.onClick();
    assert.deepEqual(h.steam, ['close menus', 'navigate /library/app/993090'], 'to its page, where Properties → Betas is');
    install.props.onClick();
    assert.ok(h.calls.some(c => c.name === 'install_lsfg'));
  }

  // Lossless Scaling not installed: its store page is one press away.
  {
    const h = harness(undefined);
    h.render();
    h.respond('get_state', { ...base, lossless_scaling: { installed: false, dll: '' } });
    await settle();
    const tree = h.render();
    assert.equal(all(tree).find(n => n.type === 'ButtonItem' && n.props.children === 'Open Lossless Scaling in the library'), undefined);
    all(tree).find(n => n.type === 'ButtonItem' && n.props.children === 'Open in the Steam Store').props.onClick();
    assert.deepEqual(h.steam, ['close menus', 'url steam://store/993090']);
  }
  console.log('frontend panel: ok');
})().catch(e => { console.error(e); process.exit(1); });
