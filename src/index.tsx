// SPDX-License-Identifier: BSD-3-Clause
// Copyright (c) 2026 Rayekkk

import { callable, definePlugin, useQuickAccessVisible } from "@decky/api";
import {
  DropdownItem, Field, Navigation, PanelSection, PanelSectionRow, Router, SliderField, staticClasses,
  ToggleField,
} from "@decky/ui";
import { FC, ReactNode, useCallback, useEffect, useState } from "react";
import { AboutPage, UpdateCheck, UpdateController, UpdateDownload, UpdateSection } from "./about";
import { Result } from "./result";
import {
  ActionButton, colors, confirmAction, infoRow, notify, PageHeader, PageShell, SectionLink, staleNote, statusPlaceholder,
} from "./ui";
import { createWriteQueue } from "./writeQueue";

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
  home: string;
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
const checkUpdates = callable<[], UpdateCheck>("check_for_updates");
const performUpdate = callable<[string], UpdateDownload>("perform_update");

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

// The page's one message area (UI.md §5): setup problems and the last failed change, until the next one succeeds.
const Note: FC<{ tone: "error" | "warning"; children: ReactNode }> = ({ tone, children }) => (
  <PanelSectionRow>
    <div role={tone === "error" ? "alert" : "status"} style={{
      padding: "8px", borderRadius: "4px", overflowWrap: "anywhere", fontSize: "12px", color: colors[tone],
      background: tone === "error" ? colors.errorSurface : colors.warningSurface,
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

const ABOUT_ICON = <><circle cx="12" cy="12" r="9" /><path d="M12 11v6m0-10h.01" /></>;

// Every change takes one road (STANDARD §3): one write at a time, the latest unsent value per game, and a poll that
// started before a change is dropped. It outlives the panel, so a reopened one never overtakes a change still on its
// way. A failed change is a toast as well as the state's error, shown until the next one succeeds.
const queue = createWriteQueue<State>(() => getState(...runningGame()), {
  onError: r => notify("DeckyLS", r.state ? r.error || "The change was not saved."
    : `The change was not saved: ${(r.error || "no answer").replace(/\.$/, "")}.`),
});

const Content: FC<{ updates?: UpdateController }> = ({ updates }) => {
  const [view, setView] = useState(queue.get());
  // What this opening has read: the state of a panel closed earlier (perhaps another game's) is not shown until then.
  const [opened, setOpened] = useState<"" | "failed" | "read">("");
  // Unsaved changes per game (ids joined), shown at once; null = the game's switch was turned off.
  const [draft, setDraft] = useState<Record<string, Settings | null>>({});
  const [showGames, setShowGames] = useState(false);
  const [showCompat, setShowCompat] = useState(false);
  const [page, setPage] = useState<"about" | null>(null);
  const [left, setLeft] = useState(false);  // About was just closed: its row takes the D-pad back
  const visible = useQuickAccessVisible();

  useEffect(() => {
    setView(queue.get());
    return queue.subscribe(() => setView(queue.get()));
  }, []);
  const refresh = useCallback(() => queue.read().then(() => {
    const now = queue.get();
    setOpened(o => o === "read" || (now.state && !now.error) ? "read" : "failed");
  }), []);
  // Decky unmounts the panel when the Quick Access Menu closes (checked on Decky 3.3.1), which ends the polling;
  // a change still waiting for its slider to settle is sent then instead of dropped.
  useEffect(() => {
    void refresh();
    const timer = setInterval(() => void refresh(), REFRESH_MS);
    return () => {
      clearInterval(timer);
      void queue.flush();
    };
  }, [refresh]);

  // A change answered without a state, such as by a dead backend, reads the state again, so the panel never quietly
  // shows the old value.
  const save = useCallback((profile: { name: string; ids: string[] }, next: Settings | null, delay = 0) => {
    const key = profile.ids.join("\n");
    setDraft(d => ({ ...d, [key]: next }));
    void queue.write(key, () => next ? setProfile(profile.ids, profile.name, pick(next), ...runningGame())
      : removeProfile(profile.ids, ...runningGame()), { delayMs: delay }).then(r => {
      if (!r.state) void refresh();
      setDraft(d => {  // a failed save shows the real state again, not the unsaved value
        if (d[key] !== next) return d;  // a newer change of this game is still on its way
        const { [key]: _, ...rest } = d;
        return rest;
      });
    });
  }, [refresh]);

  // done: the toast of a change that worked.
  const run = useCallback((action: (...a: GameArgs) => Promise<Result<State>>, done?: string, key?: string) => {
    void queue.write(key, () => action(...runningGame()), { patch: { busy: "Working…" } }).then(r => {
      if (r.ok && done) notify("DeckyLS", done);
      if (!r.state) void refresh();
    });
  }, [refresh]);

  const state = opened === "read" ? view.state : null;
  if (!state) return (
    <>
      {statusPlaceholder({ label: "DeckyLS unavailable", error: opened && view.error, onRetry: () => void refresh() })}
      {/* A plugin that does not start can still fetch the release that fixes it. */}
      {opened === "failed" && updates &&
        <UpdateSection controller={updates} version={__PLUGIN_VERSION__} home={view.state?.home ?? ""} />}
    </>
  );

  if (page === "about") {
    const close = () => { setLeft(true); setPage(null); };
    return (
      <PageShell onBack={close}>
        <PageHeader title="About" back="DeckyLS" onBack={close} focus={visible} />
        <AboutPage name="DeckyLS" version={state.version} license="BSD-3-Clause" source="github.com/Rayekkk/DeckyLS"
          description="Lossless Scaling frame generation for the game you are playing: one menu, no launch options."
          notes="Copyright (c) 2026 Rayekkk. Not affiliated with or endorsed by PancakeTAS, THS or Valve."
          credits={[
            ["lsfg-vk", "By PancakeTAS · CC BY-NC-ND 4.0. DeckyLS downloads the unmodified official build."],
            ["Lossless Scaling", "By THS. Bought in Steam; frame generation uses its files."],
          ]}
          updates={updates} home={state.home} />
      </PageShell>
    );
  }

  const installed = state.lsfg !== null;
  const ls = state.lossless_scaling;
  const game = state.game;
  const others = state.games.filter(e => isListed(e.appid) && (!game || !e.ids.some(i => game.ids.includes(i))))
    .sort((a, b) => byName.compare(a.name, b.name));

  return (
    <>
      {view.error && <PanelSection>{infoRow(staleNote(Date.now() - view.readAt), view.error)}</PanelSection>}

      {(!installed || !ls.dll || state.error || state.config_error || state.rivals.length > 0) && (
        <PanelSection title="Setup">
          {!installed && (
            <PanelSectionRow>
              <ActionButton disabled={!!state.busy} onClick={() => run(installLsfg)}
                description="Downloads the official lsfg-vk build from builds.lsfg-vk.dev and installs it in ~/.local.">
                {state.busy || `Install lsfg-vk ${state.pinned}`}
              </ActionButton>
            </PanelSectionRow>
          )}
          {!ls.installed && (
            <>
              <Note tone="warning">Install Lossless Scaling from Steam. Frame generation uses its files, so it must be bought and installed.</Note>
              <PanelSectionRow>
                <ActionButton
                  onClick={() => openInSteam(() => SteamClient.URL.ExecuteSteamURL(`steam://store/${LOSSLESS_SCALING}`))}>
                  Open in the Steam Store
                </ActionButton>
              </PanelSectionRow>
            </>
          )}
          {ls.installed && !ls.dll && (
            <>
              <Note tone="warning">In Steam, open Lossless Scaling → Properties → Betas and choose "lsfg-vk", then let it update.</Note>
              <PanelSectionRow>
                <ActionButton description="Then press the gear icon → Properties → Betas."
                  onClick={() => openInSteam(() => Navigation.Navigate(`/library/app/${LOSSLESS_SCALING}`))}>
                  Open Lossless Scaling in the library
                </ActionButton>
              </PanelSectionRow>
            </>
          )}
          {state.rivals.length > 0 && <Note tone="warning">Also installed: {state.rivals.join(", ")}. Use only one plugin to manage lsfg-vk.</Note>}
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
                  <ActionButton onClick={() => setShowCompat(v => !v)}
                    description={showCompat ? undefined : "Only if this game has problems with frame generation."}>
                    {showCompat ? "Hide compatibility options" : "Compatibility options"}
                  </ActionButton>
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
                    <div style={{ fontSize: "12px", color: colors.muted }}>
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
            <ActionButton onClick={() => setShowGames(v => !v)}
              description={showGames ? undefined
                : "Turn a game on before you start it; while it runs, choose its multiplier above."}>
              {showGames ? "Hide games" : `Show games (${others.filter(e => e.settings).length} on)`}
            </ActionButton>
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
            onChange={v => run((...g) => setFp16(v, ...g), undefined, "fp16")} />
        </PanelSectionRow>
      </PanelSection>

      <PanelSection title="lsfg-vk">
        {infoRow(installed ? `Version ${state.lsfg!.version || "—"}` : "Not installed", installed
          ? `${state.managed ? "" : "Installed by something else. "}${state.lsfg!.ok ? "Healthy." : state.lsfg!.text}`
          : undefined)}
        {state.managed && state.managed_version !== state.pinned && (
          <PanelSectionRow>
            <ActionButton disabled={!!state.busy} onClick={() => run(installLsfg)}>
              {state.busy || `Update lsfg-vk to ${state.pinned}`}
            </ActionButton>
          </PanelSectionRow>
        )}
        {state.managed && (
          <PanelSectionRow>
            <ActionButton disabled={!!state.busy} onClick={() => confirmAction("Remove lsfg-vk?",
              "DeckyLS deletes the lsfg-vk files it installed, so frame generation stops until you install it again. Your game settings stay.",
              "Remove", () => run(removeLsfg, "lsfg-vk was removed. Your game settings stay."), { destructive: true })}>
              Remove lsfg-vk
            </ActionButton>
          </PanelSectionRow>
        )}
      </PanelSection>

      <PanelSection>
        <SectionLink title="About" icon={ABOUT_ICON} focus={left && visible} onOpen={() => setPage("about")}
          description={`Version ${state.version} · updates`} />
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

export default definePlugin(() => {
  // The updater belongs to the plugin, not the panel: closing the menu keeps a check or download going.
  const updates = new UpdateController({ check: checkUpdates, download: performUpdate }, "deckyls");
  return {
    name: "DeckyLS",
    titleView: <div className={staticClasses.Title}>DeckyLS</div>,
    content: <Content updates={updates} />,
    icon: <LsIcon />,
    onDismount: () => {
      updates.dispose();
      queue.dispose();
    },
  };
});
