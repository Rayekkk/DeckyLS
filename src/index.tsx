// SPDX-License-Identifier: BSD-3-Clause
// Copyright (c) 2026 Rayekkk

import { callable, definePlugin } from "@decky/api";
import {
  ButtonItem, DropdownItem, Field, PanelSection, PanelSectionRow, Router, SliderField, Spinner, staticClasses,
  ToggleField,
} from "@decky/ui";
import { FC, useCallback, useEffect, useState } from "react";

// lsfg-vk profile keys, exactly as the backend accepts them.
interface Settings {
  multiplier: number; flow_scale: number; performance_mode: boolean;
  override_present_mode: boolean; preserve_swapchain_image_count: boolean;
}
interface Profile extends Settings { name: string; ids: string[] }
// An installed game (appid 0: a profile that matches no installed game); settings null = never set up.
interface Entry { appid: number; name: string; ids: string[]; settings: Profile | null }

interface State {
  version: string;
  pinned: string;
  lsfg: { ok: boolean; text: string; version: string } | null;
  managed: boolean;
  managed_version: string;
  busy: string;
  error: string;
  lossless_scaling: { installed: boolean; dll: string };
  rivals: string[];
  config_error: string;
  allow_fp16: boolean;
  games: Entry[];
  game: {
    appid: number; name: string; ids: string[]; running: boolean;
    settings: Profile | null;
    attached: { profile: string; via: string } | null;
  } | null;
}

type GameArgs = [appid: number, name: string];
const getState = callable<GameArgs, State>("get_state");
const setProfile = callable<[string[], string, Settings, ...GameArgs], State>("set_profile");
const removeProfile = callable<[string[], ...GameArgs], State>("remove_profile");
const setFp16 = callable<[boolean, ...GameArgs], State>("set_fp16");
const installLsfg = callable<GameArgs, State>("install_lsfg");
const removeLsfg = callable<GameArgs, State>("remove_lsfg");

// A new game's settings: lsfg-vk's own defaults, except performance mode, which suits handheld GPUs.
const DEFAULTS: Settings = {
  multiplier: 2, flow_scale: 1.0, performance_mode: true, override_present_mode: true,
  preserve_swapchain_image_count: false,
};
const pick = (s: Settings): Settings => ({
  multiplier: s.multiplier, flow_scale: s.flow_scale, performance_mode: s.performance_mode,
  override_present_mode: s.override_present_mode, preserve_swapchain_image_count: s.preserve_swapchain_image_count,
});
const MULTIPLIERS = [{ data: 1, label: "Off" }, ...[2, 3, 4, 5, 6, 7, 8].map(m => ({ data: m, label: `${m}×` }))];
const SAVE_DELAY_MS = 400; // the slider reports every step; lsfg-vk reloads the game's config on every write
const REFRESH_MS = 5000;
// Alphabetical as people read it in the Steam client's language: case and accents do not split the list.
const byName = new Intl.Collator(undefined, { sensitivity: "base", numeric: true });

const runningGame = (): GameArgs => {
  const app = Router.MainRunningApp;
  return app ? [Number(app.appid), String(app.display_name ?? "")] : [0, ""];
};

const Note: FC<{ tone: "error" | "warn"; children: any }> = ({ tone, children }) => (
  <PanelSectionRow>
    <div style={{
      padding: "8px", borderRadius: "4px", overflowWrap: "anywhere", fontSize: "12px",
      background: tone === "error" ? "rgba(248,113,113,.14)" : "rgba(250,204,21,.12)",
      color: tone === "error" ? "var(--gpColor-Red, #f87171)" : "var(--gpColor-Yellow, #facc15)",
    }}>{children}</div>
  </PanelSectionRow>
);

function status(game: NonNullable<State["game"]>): string {
  const s = game.settings;
  if (!s || s.multiplier === 1) return "Off.";
  if (game.attached?.profile === s.name) return `On: lsfg-vk is running in this game (found by ${game.attached.via}).`;
  if (game.attached) return `lsfg-vk uses the profile "${game.attached.profile}" for this game.`;
  return "Restart the game to start frame generation. lsfg-vk joins a game when it starts; OpenGL games are not supported.";
}

// One pending save per game, so a slider still settling never swallows a switch flipped on another game.
const saveTimers: Record<string, ReturnType<typeof setTimeout>> = {};

const Content: FC = () => {
  const [state, setState] = useState<State | null>(null);
  // Unsaved changes per game (ids joined), shown at once; null = the game's switch was turned off.
  const [draft, setDraft] = useState<Record<string, Settings | null>>({});
  const [confirmRemove, setConfirmRemove] = useState(false);
  const [showGames, setShowGames] = useState(false);
  const [showCompat, setShowCompat] = useState(false);

  const refresh = useCallback(() => getState(...runningGame()).then(setState, () => {}), []);
  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, REFRESH_MS);
    return () => { clearInterval(timer); Object.values(saveTimers).forEach(clearTimeout); };
  }, [refresh]);

  const save = useCallback((profile: { name: string; ids: string[] }, next: Settings | null, delay = 0) => {
    const key = profile.ids.join("\n");
    setDraft(d => ({ ...d, [key]: next }));
    clearTimeout(saveTimers[key]);
    saveTimers[key] = setTimeout(() => {
      delete saveTimers[key];
      (next ? setProfile(profile.ids, profile.name, pick(next), ...runningGame())
        : removeProfile(profile.ids, ...runningGame()))
        .then(s => { setState(s); setDraft(d => { const { [key]: _, ...rest } = d; return rest; }); }, () => {});
    }, delay);
  }, []);

  const run = useCallback((action: (...a: GameArgs) => Promise<State>) => {
    setState(s => s && { ...s, busy: "Working…" });
    action(...runningGame()).then(setState, () => refresh());
  }, [refresh]);

  if (!state) return <PanelSection><PanelSectionRow><Spinner /></PanelSectionRow></PanelSection>;

  const installed = state.lsfg !== null;
  const ls = state.lossless_scaling;
  const game = state.game;
  const others = state.games.filter(e => !game || !e.ids.some(i => game.ids.includes(i)))
    .sort((a, b) => byName.compare(a.name, b.name));

  return (
    <>
      {(!installed || !ls.dll || state.error || state.config_error || state.rivals.length > 0) && (
        <PanelSection title="Setup">
          {!installed && (
            <PanelSectionRow>
              <ButtonItem layout="below" disabled={!!state.busy} onClick={() => run(installLsfg)}
                description="Downloads the official lsfg-vk build from builds.lsfg-vk.dev and installs it in ~/.local.">
                {state.busy || `Install lsfg-vk ${state.pinned}`}
              </ButtonItem>
            </PanelSectionRow>
          )}
          {!ls.installed && <Note tone="warn">Install Lossless Scaling from Steam. Frame generation uses its files, so it must be bought and installed.</Note>}
          {ls.installed && !ls.dll && <Note tone="warn">In Steam, open Lossless Scaling → Properties → Betas and choose "lsfg-vk", then let it update.</Note>}
          {state.rivals.length > 0 && <Note tone="warn">Also installed: {state.rivals.join(", ")}. Use only one plugin to manage lsfg-vk.</Note>}
          {state.config_error && <Note tone="error">{state.config_error}</Note>}
          {state.error && <Note tone="error">{state.error}</Note>}
        </PanelSection>
      )}

      <PanelSection title={game ? game.name || `App ${game.appid}` : "Frame generation"}>
        {!game && (
          <PanelSectionRow>
            <Field focusable label="No game running" description="Start a game, then open this menu to set up frame generation for it." />
          </PanelSectionRow>
        )}
        {game && (() => {
          const profile = { name: game.name || game.ids[0], ids: game.ids };
          const saved = draft[game.ids.join("\n")] ?? game.settings;
          const s = saved ?? DEFAULTS;
          const on = !!saved && s.multiplier > 1;
          const disabled = !installed || !!state.config_error;
          return (
            <>
              <PanelSectionRow>
                <DropdownItem label="Frame generation" disabled={disabled} rgOptions={MULTIPLIERS}
                  selectedOption={on ? s.multiplier : 1}
                  description="Multiplies the game's frame rate: 40 fps at 2× shows 80. Best when the result matches your screen's refresh rate."
                  onChange={o => save(profile, { ...s, multiplier: o.data })} />
              </PanelSectionRow>
              {on && (
                <>
                  <PanelSectionRow>
                    <SliderField label="Flow scale" disabled={disabled} value={Math.round(s.flow_scale * 100)}
                      min={25} max={100} step={5} showValue valueSuffix="%"
                      description="Lower is faster, higher tracks motion better."
                      onChange={v => save(profile, { ...s, flow_scale: v / 100 }, SAVE_DELAY_MS)} />
                  </PanelSectionRow>
                  <PanelSectionRow>
                    <ToggleField label="Performance mode" disabled={disabled} checked={s.performance_mode}
                      description="A lighter model; recommended on handhelds."
                      onChange={v => save(profile, { ...s, performance_mode: v })} />
                  </PanelSectionRow>
                </>
              )}
              <PanelSectionRow>
                <Field focusable label="Status" description={status(game)} />
              </PanelSectionRow>
              {saved && (
                <PanelSectionRow>
                  <ButtonItem layout="below" onClick={() => setShowCompat(v => !v)}
                    description={showCompat ? undefined : "Only if this game has problems with frame generation."}>
                    {showCompat ? "Hide compatibility options" : "Compatibility options"}
                  </ButtonItem>
                </PanelSectionRow>
              )}
              {saved && showCompat && (
                <>
                  <PanelSectionRow>
                    <ToggleField label="Force V-Sync" disabled={disabled} checked={s.override_present_mode}
                      description="On by default: frame generation needs it to space frames evenly. Turn off only if the game misbehaves with it."
                      onChange={v => save(profile, { ...s, override_present_mode: v })} />
                  </PanelSectionRow>
                  <PanelSectionRow>
                    <ToggleField label="Keep the game's buffer count" disabled={disabled}
                      checked={s.preserve_swapchain_image_count}
                      description="Try this if the game crashes with frame generation. Can cause stutter in other games."
                      onChange={v => save(profile, { ...s, preserve_swapchain_image_count: v })} />
                  </PanelSectionRow>
                  <PanelSectionRow>
                    <div style={{ fontSize: "12px", color: "var(--gpSystemLighterGrey, #b8bcbf)" }}>
                      These two apply the next time the game starts.
                    </div>
                  </PanelSectionRow>
                </>
              )}
            </>
          );
        })()}
      </PanelSection>

      {others.length > 0 && (
        <PanelSection title="Games">
          <PanelSectionRow>
            <ButtonItem layout="below" onClick={() => setShowGames(v => !v)}
              description={showGames ? undefined
                : "Turn a game on before you start it; while it runs, choose its multiplier above."}>
              {showGames ? "Hide games" : `Show games (${others.filter(e => e.settings).length} on)`}
            </ButtonItem>
          </PanelSectionRow>
          {showGames && others.map(e => {
            const key = e.ids.join("\n");
            const s = key in draft ? draft[key] : e.settings;
            return (
              <PanelSectionRow key={key}>
                <ToggleField label={e.name || e.ids[0]} disabled={!installed || !!state.config_error} checked={!!s}
                  description={s && s.multiplier > 1 ? `${s.multiplier}× frame generation` : s ? "Ready" : undefined}
                  onChange={on => save({ name: e.name || e.ids[0], ids: e.ids }, on ? { ...DEFAULTS, multiplier: 1 } : null)} />
              </PanelSectionRow>
            );
          })}
        </PanelSection>
      )}

      <PanelSection title="All games">
        <PanelSectionRow>
          <ToggleField label="Half precision (FP16)" disabled={!installed || !!state.config_error}
            checked={state.allow_fp16}
            description="Faster on AMD graphics, such as the Steam Deck, Legion Go and ROG Ally, with the same image. Turn off only on an old NVIDIA GTX 10 card. Applies the next time a game starts."
            onChange={v => run((...g) => setFp16(v, ...g))} />
        </PanelSectionRow>
      </PanelSection>

      <PanelSection title="About">
        <PanelSectionRow>
          <Field focusable label="lsfg-vk" description={!installed ? "Not installed."
            : `${state.lsfg!.version || "unknown version"}${state.managed ? "" : " (installed by something else)"}. `
              + (state.lsfg!.ok ? "Healthy." : state.lsfg!.text)} />
        </PanelSectionRow>
        {state.managed && state.managed_version !== state.pinned && (
          <PanelSectionRow>
            <ButtonItem layout="below" disabled={!!state.busy} onClick={() => run(installLsfg)}>
              {state.busy || `Update lsfg-vk to ${state.pinned}`}
            </ButtonItem>
          </PanelSectionRow>
        )}
        {state.managed && (
          <PanelSectionRow>
            <ButtonItem layout="below" disabled={!!state.busy}
              description={confirmRemove ? "Press again to remove. Your game settings stay." : undefined}
              onClick={() => { if (!confirmRemove) return setConfirmRemove(true); setConfirmRemove(false); run(removeLsfg); }}>
              {confirmRemove ? "Confirm: remove lsfg-vk" : "Remove lsfg-vk"}
            </ButtonItem>
          </PanelSectionRow>
        )}
        <PanelSectionRow>
          <Field focusable label="DeckyLS" description={`Version ${state.version}. Uses lsfg-vk by PancakeTAS and Lossless Scaling by THS; not affiliated with either.`} />
        </PanelSectionRow>
      </PanelSection>
    </>
  );
};

const LsIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}
    strokeLinecap="round" strokeLinejoin="round" style={{ width: "1em", height: "1em" }}>
    <rect x="2.5" y="5" width="13" height="14" rx="2.5" />
    <path d="M18.5 7.5v9" />
    <path d="M21.5 9.5v5" />
  </svg>
);

export default definePlugin(() => ({
  name: "DeckyLS",
  titleView: <div className={staticClasses.Title}>DeckyLS</div>,
  content: <Content />,
  icon: <LsIcon />,
}));
