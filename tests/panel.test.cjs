// SPDX-License-Identifier: BSD-3-Clause
// The panel's real TSX with controlled hooks, RPC calls and timers (DeckyKit's frontend_harness.cjs).
const test = require('node:test');
const assert = require('node:assert/strict');
const { harness, all, find, findText, settle } = require('./frontend_harness.cjs');

/** The panel with runningApp as Steam's running game; answers are given as states and sent as { ok, state }.
 *  keep: more components left as elements; ui: more @decky/ui members (e.g. showModal). Calls go out through the
 *  shared write queue, a microtask after the action, hence the settle() before every answer. */
function panel(runningApp, { keep = [], ui = {} } = {}) {
  const steam = [];  // what the panel asked Steam to open, in order
  // Steam app types: 1 game, 4 tool (Ubisoft Connect Services, Proton...); apps not listed have no overview.
  const appTypes = { 1145360: 1, 1809540: 1, 4099820: 4, 1493710: 4 };
  const h = harness({
    ui: {
      Router: { get MainRunningApp() { return runningApp; } },
      Navigation: { CloseSideMenus: () => steam.push('close menus'), Navigate: p => steam.push(`navigate ${p}`) },
      ...ui,
    },
    globals: {
      appStore: { GetAppOverviewByAppID: id => (id in appTypes ? { app_type: appTypes[id] } : null) },
      SteamClient: { URL: { ExecuteSteamURL: url => steam.push(`url ${url}`) } },
    },
    keep: ['Note', 'Content', ...keep],  // Content: the element definePlugin hands Decky, with its props
  });
  return { ...h, steam, answer: h.respond, respond: (name, state) => h.respond(name, { ok: true, state }) };
}

const base = {
  version: '0.1.0', home: '/home/deck', pinned: '2.0.0', lsfg: { ok: true, text: '', version: '2.0.0' }, managed: true,
  managed_version: '2.0.0', busy: '', error: '', lossless_scaling: { installed: true, dll: '/ls/lsfg-vk.dll' },
  rivals: [], config_error: '', allow_fp16: true, games: [], game: null,
};
const Q = { override_present_mode: true, preserve_swapchain_image_count: false };
const game = (settings = null, attached = null) => ({ ...base, game: {
  appid: 1809540, name: 'Nine Sols', ids: ['1809540'], running: true, settings, attached } });

test('frontend panel', async () => {
  // A running game without a profile: off; picking 2x saves the defaults for its ids at once.
  {
    const h = panel({ appid: '1809540', display_name: 'Nine Sols' });
    h.render();
    await settle();
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
    await settle();
    const saved = h.calls.find(c => c.name === 'set_profile');
    assert.deepEqual(saved.args, [['1809540'], 'Nine Sols', { multiplier: 2, flow_scale: 1, performance_mode: true, ...Q }, 1809540, 'Nine Sols']);
    h.respond('set_profile', game({ name: 'Nine Sols', ids: ['1809540'], multiplier: 2, flow_scale: 1, performance_mode: true, ...Q }));
    await settle();
    tree = h.render();
    assert.match(find(tree, 'Field', 'Status').props.description, /Restart the game/);
  }

  // Slider steps are saved once, after the user stops moving it; attached status names how lsfg-vk found the game.
  {
    const h = panel({ appid: 1809540, display_name: 'Nine Sols' });
    h.render();
    await settle();
    const on = { name: 'Nine Sols', ids: ['1809540'], multiplier: 3, flow_scale: 1, performance_mode: true, ...Q };
    h.respond('get_state', game(on, { profile: 'Nine Sols', via: 'Steam App ID' }));
    await settle();
    let tree = h.render();
    assert.match(find(tree, 'Field', 'Status').props.description, /^On: .*Steam App ID/);
    for (const v of [95, 90, 85]) { find(h.render(), 'SliderField').props.onChange(v); }
    assert.equal(find(h.render(), 'SliderField').props.value, 85);
    h.fire();
    await settle();
    const saves = h.calls.filter(c => c.name === 'set_profile');
    assert.equal(saves.length, 1);
    assert.deepEqual(saves[0].args, [['1809540'], 'Nine Sols', { multiplier: 3, flow_scale: 0.85, performance_mode: true, ...Q }, 1809540, 'Nine Sols']);
  }

  // Closing the menu while the slider is still settling sends the change instead of dropping it.
  {
    const h = panel({ appid: 1809540, display_name: 'Nine Sols' });
    h.render();
    await settle();
    const on = { name: 'Nine Sols', ids: ['1809540'], multiplier: 2, flow_scale: 1, performance_mode: true, ...Q };
    h.respond('get_state', game(on, { profile: 'Nine Sols', via: 'Steam App ID' }));
    await settle();
    find(h.render(), 'SliderField').props.onChange(70);
    assert.ok(!h.calls.some(c => c.name === 'set_profile'), 'still waiting for the slider to settle');
    h.unmount();
    await settle();
    assert.deepEqual(h.calls.find(c => c.name === 'set_profile').args,
      [['1809540'], 'Nine Sols', { multiplier: 2, flow_scale: 0.7, performance_mode: true, ...Q }, 1809540, 'Nine Sols']);
  }

  // A save the backend rejects does not leave the unsaved value on screen; the real state is fetched instead.
  // An answer to an older change of a game never wipes a newer one still on its way.
  {
    const h = panel({ appid: 1809540, display_name: 'Nine Sols' });
    h.render();
    await settle();
    const two = { name: 'Nine Sols', ids: ['1809540'], multiplier: 2, flow_scale: 1, performance_mode: true, ...Q };
    h.respond('get_state', game(two, { profile: 'Nine Sols', via: 'Steam App ID' }));
    await settle();
    find(h.render(), 'DropdownItem', 'Frame generation').props.onChange({ data: 4 });
    h.fire();
    await settle();
    h.fail('set_profile');
    await settle();
    assert.equal(find(h.render(), 'DropdownItem', 'Frame generation').props.selectedOption, 2, 'back to what is saved');
    assert.ok(h.calls.some(c => c.name === 'get_state' && !c.settled), 'and the state is asked for at once');
    find(h.render(), 'DropdownItem', 'Frame generation').props.onChange({ data: 3 });
    h.fire();
    await settle();
    find(h.render(), 'SliderField').props.onChange(60);  // a newer change, not sent yet
    h.respond('set_profile', game({ ...two, multiplier: 3 }, { profile: 'Nine Sols', via: 'Steam App ID' }));
    await settle();
    assert.equal(find(h.render(), 'SliderField').props.value, 60, 'the newer change stays on screen');
  }

  // A poll that started before a change cannot put the old value back, and polls never stack up.
  {
    const h = panel({ appid: 1809540, display_name: 'Nine Sols' });
    h.render();
    await settle();
    const two = { name: 'Nine Sols', ids: ['1809540'], multiplier: 2, flow_scale: 1, performance_mode: true, ...Q };
    h.respond('get_state', game(two, { profile: 'Nine Sols', via: 'Steam App ID' }));
    await settle();
    h.render();
    h.tick();
    h.tick();
    await settle();
    assert.equal(h.calls.filter(c => c.name === 'get_state' && !c.settled).length, 1, 'one poll at a time');
    find(h.render(), 'DropdownItem', 'Frame generation').props.onChange({ data: 3 });
    h.fire();
    await settle();
    h.respond('set_profile', game({ ...two, multiplier: 3 }, { profile: 'Nine Sols', via: 'Steam App ID' }));
    await settle();
    h.respond('get_state', game(two, { profile: 'Nine Sols', via: 'Steam App ID' }));  // the late, outdated poll
    await settle();
    assert.equal(find(h.render(), 'DropdownItem', 'Frame generation').props.selectedOption, 3);
    h.tick();
    await settle();
    assert.equal(h.calls.filter(c => c.name === 'get_state' && !c.settled).length, 1, 'polling goes on afterwards');
    // Closed and opened again while that poll is still running: the new panel waits for it, not for the next poll,
    // and shows nothing of the old panel's state before it answers.
    h.remount();
    await settle();
    assert.equal(h.calls.filter(c => c.name === 'get_state' && !c.settled).length, 1, 'no second request');
    assert.ok(find(h.render(), 'Spinner'));
    h.respond('get_state', game({ ...two, multiplier: 3 }, { profile: 'Nine Sols', via: 'Steam App ID' }));
    await settle();
    assert.equal(find(h.render(), 'DropdownItem', 'Frame generation').props.selectedOption, 3, 'no 5 s spinner');
  }

  // Multipliers up to 8x; compatibility options are folded away and keep every other setting; FP16 is global.
  {
    const h = panel({ appid: 1809540, display_name: 'Nine Sols' });
    h.render();
    await settle();
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
    await settle();
    assert.deepEqual(h.calls.find(c => c.name === 'set_profile').args, [['1809540'], 'Nine Sols',
      { multiplier: 2, flow_scale: 0.8, performance_mode: false, override_present_mode: true,
        preserve_swapchain_image_count: true }, 1809540, 'Nine Sols'], 'only the changed key differs; no name or ids inside');
    h.respond('set_profile', game(on));
    await settle();
    find(h.render(), 'ToggleField', 'Half precision (FP16)').props.onChange(false);
    await settle();
    assert.deepEqual(h.calls.find(c => c.name === 'set_fp16').args, [false, 1809540, 'Nine Sols']);
  }

  // Games list: collapsed at first; expanded it is alphabetical without the running game. A switch turned on
  // prepares the game at 1× (the multiplier is chosen in the game), turned off it removes the game's profile.
  {
    const h = panel({ appid: 1809540, display_name: 'Nine Sols' });
    h.render();
    await settle();
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
    await settle();
    assert.deepEqual(h.calls.find(c => c.name === 'set_profile').args,
      [['2147483649', 'Game.exe'], 'Shortcut', { multiplier: 1, flow_scale: 1, performance_mode: true, ...Q }, 1809540, 'Nine Sols'], 'both switches saved, neither swallowed');
    assert.ok(!h.calls.some(c => c.name === 'remove_profile'), 'one change at a time, in the order they were made');
    h.respond('set_profile', listed);
    await settle();
    assert.deepEqual(h.calls.find(c => c.name === 'remove_profile').args, [['1145360'], 1809540, 'Nine Sols']);
    assert.equal(find(h.render(), 'ToggleField', 'Hades').props.checked, false);
  }

  // No game: a hint, the games list, and the install button when lsfg-vk is missing.
  {
    const h = panel(undefined);
    h.render();
    await settle();
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
    await settle();
    assert.ok(h.calls.some(c => c.name === 'install_lsfg'));
  }

  // Lossless Scaling not installed: its store page is one press away.
  {
    const h = panel(undefined);
    h.render();
    await settle();
    h.respond('get_state', { ...base, lossless_scaling: { installed: false, dll: '' } });
    await settle();
    const tree = h.render();
    assert.equal(all(tree).find(n => n.type === 'ButtonItem' && n.props.children === 'Open Lossless Scaling in the library'), undefined);
    all(tree).find(n => n.type === 'ButtonItem' && n.props.children === 'Open in the Steam Store').props.onClick();
    assert.deepEqual(h.steam, ['close menus', 'url steam://store/993090']);
  }

  // The first state cannot be read: a spinner until then; after, "DeckyLS unavailable", the reason and Try again,
  // with the plugin's updater under it. The next poll still tries again.
  {
    const h = panel(undefined);
    const updates = h.exports.default().content.props.updates;
    h.render({ updates });
    await settle();
    assert.ok(find(h.render({ updates }), 'Spinner'), 'never an empty panel while loading');
    h.answer('get_state', { ok: false, error: 'Unexpected error: library gone. Details are in the Decky log.' });
    await settle();
    let tree = h.render({ updates });
    const why = find(tree, 'Field', 'DeckyLS unavailable').props.description;
    assert.match(why.props.children, /^Unexpected error: library gone/);
    assert.equal(find(tree, 'Spinner'), undefined);
    assert.ok(find(tree, 'Field', 'Installed version 0.0.0-test'), 'a broken plugin can still be updated');
    all(tree).find(n => n.type === 'ButtonItem' && n.props.children === 'Try again').props.onClick();
    await settle();
    h.fail('get_state');  // the backend is gone altogether
    await settle();
    assert.equal(find(h.render({ updates }), 'Field', 'DeckyLS unavailable').props.description.props.children, 'backend gone');
    h.tick();
    await settle();
    h.respond('get_state', base);
    await settle();
    tree = h.render({ updates });
    assert.ok(find(tree, 'Field', 'No game running'), 'a later poll that works shows the panel');
    assert.equal(find(tree, 'Field', 'DeckyLS unavailable'), undefined);
  }

  // A poll that fails after a state keeps the values on screen and says how old they are, until one works again.
  {
    const h = panel(undefined);
    h.render();
    await settle();
    h.respond('get_state', base);
    await settle();
    h.render();
    h.advance(5000);
    await settle();
    h.fail('get_state');
    await settle();
    let tree = h.render();
    assert.equal(find(tree, 'Field', 'Last read 5s ago · Retrying…').props.description, 'backend gone');
    assert.ok(find(tree, 'Field', 'No game running'), 'the last state stays');
    h.advance(5000);
    await settle();
    h.respond('get_state', base);
    await settle();
    assert.equal(findText(h.render(), 'Last read'), undefined);
  }

  // Removing lsfg-vk deletes files: it asks first, with Steam's warning, and the outcome is a toast.
  {
    const modals = [];
    const h = panel(undefined, { ui: { showModal: m => modals.push(m) } });
    h.render();
    await settle();
    h.respond('get_state', base);
    await settle();
    const tree = h.render();
    assert.equal(find(tree, 'Field', 'Version 2.0.0').props.description, 'Healthy.', 'lsfg-vk stays on the main page');
    all(tree).find(n => n.type === 'ButtonItem' && n.props.children === 'Remove lsfg-vk').props.onClick();
    assert.ok(!h.calls.some(c => c.name === 'remove_lsfg'), 'nothing removed before the answer');
    const [modal] = modals;
    assert.deepEqual([modal.type, modal.props.strTitle, modal.props.strOKButtonText, modal.props.strCancelButtonText,
      modal.props.bDestructiveWarning], ['ConfirmModal', 'Remove lsfg-vk?', 'Remove', 'Cancel', true]);
    assert.match(modal.props.strDescription, /Your game settings stay\.$/);
    modal.props.onCancel?.();
    assert.ok(!h.calls.some(c => c.name === 'remove_lsfg'), 'Cancel removes nothing');
    modal.props.onOK();
    await settle();
    h.answer('remove_lsfg', { ok: false, error: 'Could not remove lsfg-vk: Permission denied', state: { ...base,
      error: 'Could not remove lsfg-vk: Permission denied' } });
    await settle();
    assert.deepEqual(h.toasts.map(t => t.body), ['Could not remove lsfg-vk: Permission denied'], 'a failure is a toast too');
    h.toasts.length = 0;
    all(h.render()).find(n => n.type === 'ButtonItem' && n.props.children === 'Remove lsfg-vk').props.onClick();
    modals.at(-1).props.onOK();
    await settle();
    h.respond('remove_lsfg', { ...base, lsfg: null, managed: false, managed_version: '' });
    await settle();
    assert.deepEqual(h.toasts.map(t => [t.title, t.body]), [['DeckyLS', 'lsfg-vk was removed. Your game settings stay.']]);
    assert.ok(find(h.render(), 'Field', 'Not installed'));
  }

  // About is the last row and opens a page: version, author, credits, and the plugin's updater at the very bottom.
  // B (or ‹ DeckyLS) goes back, and the D-pad returns to the About row.
  {
    const h = panel(undefined, { keep: ['SectionLink', 'PageHeader'] });
    const plugin = h.exports.default();
    const updates = plugin.content.props.updates;
    h.render({ updates });
    await settle();
    h.respond('get_state', base);
    await settle();
    let tree = h.render({ updates });
    const sections = all(tree).filter(n => n.type === 'PanelSection');
    const link = all(sections.at(-1)).find(n => n.type?.name === 'SectionLink');
    assert.deepEqual([link.props.title, link.props.description, link.props.focus], ['About', 'Version 0.1.0 · updates', false]);
    link.props.onOpen();
    tree = h.render({ updates });
    const header = all(tree).find(n => n.type?.name === 'PageHeader');
    assert.deepEqual([header.props.title, header.props.back, header.props.focus], ['About', 'DeckyLS', true]);
    assert.match(find(tree, 'Field', 'Version 0.1.0').props.description, /^Lossless Scaling frame generation/);
    assert.ok(findText(tree, 'Rayek · BSD-3-Clause · github.com/Rayekkk/DeckyLS'));
    assert.match(find(tree, 'Field', 'lsfg-vk').props.description, /PancakeTAS · CC BY-NC-ND 4\.0/);
    assert.match(find(tree, 'Field', 'Lossless Scaling').props.description, /^By THS/);
    assert.equal(all(tree).find(n => n.type === 'ButtonItem' && /lsfg-vk/.test(n.props.children)), undefined,
      'installing and removing lsfg-vk are not in About');
    assert.equal(all(tree).filter(n => n.type === 'PanelSection').at(-1).props.title, 'Updates');
    assert.equal(find(tree, 'Field', 'Installed version 0.1.0').props.description, 'Check for updates when you need them.');

    all(tree).find(n => n.type === 'ButtonItem' && n.props.children === 'Check for updates').props.onClick();
    assert.deepEqual(h.calls.at(-1).args, []);
    h.answer('check_for_updates', { ok: true, current_version: '0.1.0', latest_version: '0.6.0', update_available: true,
      download_available: true, asset_name: 'DeckyLS-0.6.0.zip', size: 1048576 });
    await settle();
    tree = h.render({ updates });
    assert.equal(find(tree, 'Field', 'Update available').props.description, 'Version 0.6.0 (1.0 MB).');
    all(tree).find(n => n.type === 'ButtonItem' && n.props.children === 'Download 0.6.0').props.onClick();
    assert.deepEqual(h.calls.at(-1).args, ['0.6.0']);
    h.answer('perform_update', { ok: true, path: '/home/deck/Downloads/DeckyLS-0.6.0.zip', version: '0.6.0', sha256: 'x' });
    await settle();
    tree = h.render({ updates });
    assert.ok(find(tree, 'Field', '0.6.0 downloaded'));
    assert.ok(all(tree).some(n => [].concat(n.props?.children ?? []).join('') === 'Saved to ~/Downloads/DeckyLS-0.6.0.zip.'),
      'the path without the user name');

    find(tree, 'Focusable').props.onCancelButton({ preventDefault() {}, stopPropagation() {} });
    tree = h.render({ updates });
    assert.equal(all(tree).find(n => n.type?.name === 'SectionLink').props.focus, true, 'back on the About row');
    const asked = h.calls.length;
    plugin.onDismount();
    await updates.run('check');
    assert.equal(h.calls.length, asked, 'an unloaded plugin sends nothing');
  }

  // A refused change answers with the state, whose error stays on screen.
  {
    const h = panel({ appid: 1809540, display_name: 'Nine Sols' });
    h.render();
    await settle();
    h.respond('get_state', game());
    await settle();
    find(h.render(), 'ToggleField', 'Half precision (FP16)').props.onChange(false);
    await settle();
    h.answer('set_fp16', { ok: false, error: 'No.', state: { ...game(), error: 'No.' } });
    await settle();
    assert.ok(all(h.render()).some(n => n.type?.name === 'Note' && n.props.children === 'No.'));
    assert.deepEqual(h.toasts.map(t => [t.title, t.body]), [['DeckyLS', 'No.']], 'and a toast titled with the plugin');
    assert.ok(!h.calls.some(c => c.name === 'get_state' && !c.settled), 'the answer had the state, nothing to ask');
  }

  // A change that fails without a state (the backend is gone) says so in a toast and shows the real state again.
  {
    const h = panel({ appid: 1809540, display_name: 'Nine Sols' });
    h.render();
    await settle();
    h.respond('get_state', game());
    await settle();
    find(h.render(), 'DropdownItem', 'Frame generation').props.onChange({ data: 3 });
    h.fire();
    await settle();
    h.fail('set_profile');
    await settle();
    assert.deepEqual(h.toasts.map(t => [t.title, t.body]), [['DeckyLS', 'The change was not saved: backend gone.']]);
    h.respond('get_state', game());
    await settle();
    assert.equal(find(h.render(), 'DropdownItem', 'Frame generation').props.selectedOption, 1, 'not the unsaved 3×');
    find(h.render(), 'ToggleField', 'Half precision (FP16)').props.onChange(false);
    await settle();
    h.fail('set_fp16');
    await settle();
    assert.equal(h.toasts.length, 2, 'the same for the FP16 switch and the lsfg-vk buttons');
  }

});
