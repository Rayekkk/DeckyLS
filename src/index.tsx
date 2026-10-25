// SPDX-License-Identifier: BSD-3-Clause
// Copyright (c) 2026 Rayekkk

import { callable, definePlugin } from "@decky/api";
import {
  ButtonItem, DropdownItem, Field, PanelSection, PanelSectionRow, Router, SliderField, Spinner, staticClasses,
  ToggleField,
} from "@decky/ui";
import { FC, useCallback, useEffect, useState } from "react";

interface Settings { multiplier: number; flow_scale: number; performance_mode: boolean }
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
  games: Entry[];
  game: {
    appid: number; name: string; ids: string[]; running: boolean;
    settings: Profile | null;
    attached: { profile: string; via: string } | null;
  } | null;
}

type GameArgs = [appid: number, name: string];
const getState = callable<GameArgs, State>("get_state");
const setProfile = callable<[string[], string, number, number, boolean, number], State>("set_profile");
const installLsfg = callable<GameArgs, State>("install_lsfg");
const removeLsfg = callable<GameArgs, State>("remove_lsfg");

const DEFAULTS: Settings = { multiplier: 2, flow_scale: 1.0, performance_mode: true };
const MULTIPLIERS = [
  { data: 1, label: "Off" }, { data: 2, label: "2×" }, { data: 3, label: "3×" }, { data: 4, label: "4×" },
];
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

let saveTimer: ReturnType<typeof setTimeout> | undefined;

const Content: FC = () => {
  const [state, setState] = useState<State | null>(null);
  const [draft, setDraft] = useState<Record<string, Settings>>({});
  const [confirmRemove, setConfirmRemove] = useState(false);

  const refresh = useCallback(() => getState(...runningGame()).then(setState, () => {}), []);
  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, REFRESH_MS);
    return () => { clearInterval(timer); if (saveTimer) clearTimeout(saveTimer); };
  }, [refresh]);

  const save = useCallback((profile: { name: string; ids: string[] }, next: Settings, delay = 0) => {
    const key = profile.ids.join("\n");
    setDraft(d => ({ ...d, [key]: next }));
    if (saveTimer) clearTimeout(saveTimer);
    saveTimer = setTimeout(() => {
      saveTimer = undefined;
      setProfile(profile.ids, profile.name, next.multiplier, next.flow_scale, next.performance_mode, runningGame()[0])
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
            </>
          );
        })()}
      </PanelSection>

      {others.length > 0 && (
        <PanelSection title="Games">
          <PanelSectionRow>
            <div style={{ fontSize: "12px", color: "var(--gpSystemLighterGrey, #b8bcbf)" }}>
              Set a game up before you start it and frame generation runs from its first frame.
            </div>
          </PanelSectionRow>
          {others.map(e => {
            const s = draft[e.ids.join("\n")] ?? e.settings ?? { ...DEFAULTS, multiplier: 1 };
            return (
              <PanelSectionRow key={e.ids.join("\n")}>
                <DropdownItem label={e.name || e.ids[0]} disabled={!installed || !!state.config_error}
                  rgOptions={MULTIPLIERS} selectedOption={s.multiplier}
                  onChange={o => save({ name: e.name || e.ids[0], ids: e.ids }, { ...s, multiplier: o.data })} />
              </PanelSectionRow>
            );
          })}
        </PanelSection>
      )}

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
