// SPDX-License-Identifier: BSD-3-Clause
// Copyright (c) 2026 Rayekkk

import { callable, definePlugin } from "@decky/api";
import {
  ButtonItem, DropdownItem, Field, Navigation, PanelSection, PanelSectionRow, Router, SliderField, Spinner,
  staticClasses, ToggleField,
} from "@decky/ui";
import { FC, ReactNode, useCallback, useEffect, useState } from "react";
import { Result, settle, toastError } from "./result";

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

// Every method answers with the panel's state; a refused change also sets state.error, shown until the next one.
type GameArgs = [appid: number, name: string];
const getState = callable<GameArgs, Result<State>>("get_state");
const setProfile = callable<[string[], string, Settings, ...GameArgs], Result<State>>("set_profile");
const removeProfile = callable<[string[], ...GameArgs], Result<State>>("remove_profile");
const setFp16 = callable<[boolean, ...GameArgs], Result<State>>("set_fp16");
const installLsfg = callable<GameArgs, Result<State>>("install_lsfg");
const removeLsfg = callable<GameArgs, Result<State>>("remove_lsfg");

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

const LOSSLESS_SCALING = 993090;
// Steam's app types worth listing: game, application, demo, non-Steam shortcut. Tools (Proton, runtimes,
// redistributables, launcher services such as Ubisoft Connect Services) are left out.
const LISTED_TYPES = new Set([1, 2, 8, 0x40000000]);
const isListed = (appid: number) => {
  if (!appid) return true;  // a profile that matches no installed game
  try {
    const type = appStore?.GetAppOverviewByAppID(appid)?.app_type;
    return type === undefined || LISTED_TYPES.has(type);
  } catch {
    return true;
  }
};

const openInSteam = (open: () => void) => {
  Navigation.CloseSideMenus();
  open();
};

const runningGame = (): GameArgs => {
  const app = Router.MainRunningApp;
  return app ? [Number(app.appid), String(app.display_name ?? "")] : [0, ""];
};

const Note: FC<{ tone: "error" | "warn"; children: ReactNode }> = ({ tone, children }) => (
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
// Closing the menu sends what is still pending instead of dropping it.
const pendingSaves: Record<string, { timer: ReturnType<typeof setTimeout>; send: () => void }> = {};
// Bumped by every change: a poll that started before the latest change answers with an outdated state.
let changeSeq = 0;
let polling = false;  // a slow poll is not stacked with the next one

const Content: FC = () => {
  const [state, setState] = useState<State | null>(null);
  const [loadError, setLoadError] = useState("");  // why the first state could not be read; polling retries
  // Unsaved changes per game (ids joined), shown at once; null = the game's switch was turned off.
  const [draft, setDraft] = useState<Record<string, Settings | null>>({});
  const [confirmRemove, setConfirmRemove] = useState(false);
  const [showGames, setShowGames] = useState(false);
  const [showCompat, setShowCompat] = useState(false);

  // first: a panel just opened always asks, even if the poll of a panel closed a moment ago is still running.
  const refresh = useCallback((first = false) => {
    if (polling && !first) return;
    polling = true;
    const seq = changeSeq;
    settle(getState(...runningGame())).then(r => {
      if (seq !== changeSeq) return;
      if (r.state) setState(r.state);
      setLoadError(r.state ? "" : r.error ?? "");  // a failed poll keeps the last state on screen
    }).finally(() => { polling = false; });
  }, []);
  // Decky unmounts the panel when the Quick Access Menu closes (checked on Decky 3.3.1), which ends the polling.
  useEffect(() => {
    refresh(true);
    const timer = setInterval(() => refresh(), REFRESH_MS);
    return () => {
      clearInterval(timer);
      for (const pending of Object.values(pendingSaves)) {
        clearTimeout(pending.timer);
        pending.send();
      }
    };
  }, [refresh]);

  // An answer with the state shows it (a refusal's error is in it); one without, such as a dead backend, shows the
  // error as a toast and reads the state again, so the panel never quietly shows the old value.
  const showAnswer = useCallback((r: Result<State>) => {
    if (r.state) return setState(r.state);
    toastError(r, "DeckyLS: the change was not saved");
    refresh(true);
  }, [refresh]);

  const save = useCallback((profile: { name: string; ids: string[] }, next: Settings | null, delay = 0) => {
    const key = profile.ids.join("\n");
    setDraft(d => ({ ...d, [key]: next }));
    const send = () => {
      delete pendingSaves[key];
      changeSeq++;
      // A failed save shows the real state again, not the unsaved value.
      settle(next ? setProfile(profile.ids, profile.name, pick(next), ...runningGame())
        : removeProfile(profile.ids, ...runningGame()))
        .then(showAnswer)
        .finally(() => setDraft(d => {
          if (d[key] !== next) return d;  // a newer change of this game is still on its way
          const { [key]: _, ...rest } = d;
          return rest;
        }));
    };
    clearTimeout(pendingSaves[key]?.timer);
    pendingSaves[key] = { timer: setTimeout(send, delay), send };
  }, [showAnswer]);

  const run = useCallback((action: (...a: GameArgs) => Promise<Result<State>>) => {
    changeSeq++;
    setState(s => s && { ...s, busy: "Working…" });
    settle(action(...runningGame())).then(showAnswer);
  }, [showAnswer]);

  if (!state) return (
    <PanelSection>
      {loadError ? <Note tone="error">DeckyLS could not read its state: {loadError}</Note>
        : <PanelSectionRow><Spinner /></PanelSectionRow>}
    </PanelSection>
  );

  const installed = state.lsfg !== null;
  const ls = state.lossless_scaling;
  const game = state.game;
  const others = state.games.filter(e => isListed(e.appid) && (!game || !e.ids.some(i => game.ids.includes(i))))
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
          {!ls.installed && (
            <>
              <Note tone="warn">Install Lossless Scaling from Steam. Frame generation uses its files, so it must be bought and installed.</Note>
              <PanelSectionRow>
                <ButtonItem layout="below"
                  onClick={() => openInSteam(() => SteamClient.URL.ExecuteSteamURL(`steam://store/${LOSSLESS_SCALING}`))}>
                  Open in the Steam Store
                </ButtonItem>
              </PanelSectionRow>
            </>
          )}
          {ls.installed && !ls.dll && (
            <>
              <Note tone="warn">In Steam, open Lossless Scaling → Properties → Betas and choose "lsfg-vk", then let it update.</Note>
              <PanelSectionRow>
                <ButtonItem layout="below" description="Then press the gear icon → Properties → Betas."
                  onClick={() => openInSteam(() => Navigation.Navigate(`/library/app/${LOSSLESS_SCALING}`))}>
                  Open Lossless Scaling in the library
                </ButtonItem>
              </PanelSectionRow>
            </>
          )}
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
