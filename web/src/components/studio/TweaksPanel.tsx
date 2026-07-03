"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type CSSProperties,
  type PointerEvent,
  type ReactNode,
} from "react";

const PANEL_PAD = 16;

const TWEAKS_STYLE = `
  .twk-launch{position:fixed;right:18px;bottom:18px;z-index:70;height:38px;padding:0 13px;
    border:1px solid var(--border-coral);border-radius:14px;background:rgba(255,255,255,.86);
    color:var(--primary);box-shadow:var(--shadow-lg);backdrop-filter:blur(18px) saturate(160%);
    font:800 12px/1 var(--font-display);cursor:pointer}
  .twk-panel{position:fixed;right:16px;bottom:16px;z-index:70;width:280px;
    max-height:calc(100vh - 32px);display:flex;flex-direction:column;
    background:rgba(250,249,247,.78);color:#29261b;
    -webkit-backdrop-filter:blur(24px) saturate(160%);backdrop-filter:blur(24px) saturate(160%);
    border:.5px solid rgba(255,255,255,.6);border-radius:14px;
    box-shadow:0 1px 0 rgba(255,255,255,.5) inset,0 12px 40px rgba(0,0,0,.18);
    font:11.5px/1.4 ui-sans-serif,system-ui,-apple-system,sans-serif;overflow:hidden}
  .twk-hd{display:flex;align-items:center;justify-content:space-between;
    padding:10px 8px 10px 14px;cursor:move;user-select:none}
  .twk-hd b{font-size:12px;font-weight:600;letter-spacing:.01em}
  .twk-x{appearance:none;border:0;background:transparent;color:rgba(41,38,27,.55);
    width:22px;height:22px;border-radius:6px;cursor:pointer;font-size:13px;line-height:1}
  .twk-x:hover{background:rgba(0,0,0,.06);color:#29261b}
  .twk-body{padding:2px 14px 14px;display:flex;flex-direction:column;gap:10px;
    overflow-y:auto;overflow-x:hidden;min-height:0;scrollbar-width:thin;
    scrollbar-color:rgba(0,0,0,.15) transparent}
  .twk-row{display:flex;flex-direction:column;gap:5px}
  .twk-row-h{flex-direction:row;align-items:center;justify-content:space-between;gap:10px}
  .twk-lbl{display:flex;justify-content:space-between;align-items:baseline;color:rgba(41,38,27,.72)}
  .twk-lbl>span:first-child{font-weight:500}
  .twk-val{color:rgba(41,38,27,.5);font-variant-numeric:tabular-nums}
  .twk-sect{font-size:10px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;
    color:rgba(41,38,27,.45);padding:10px 0 0}
  .twk-sect:first-child{padding-top:0}
  .twk-field{appearance:none;box-sizing:border-box;width:100%;min-width:0;height:26px;padding:0 8px;
    border:.5px solid rgba(0,0,0,.1);border-radius:7px;background:rgba(255,255,255,.6);
    color:inherit;font:inherit;outline:none}
  .twk-field:focus{border-color:rgba(0,0,0,.25);background:rgba(255,255,255,.85)}
  .twk-slider{appearance:none;-webkit-appearance:none;width:100%;height:4px;margin:6px 0;
    border-radius:999px;background:rgba(0,0,0,.12);outline:none}
  .twk-slider::-webkit-slider-thumb{-webkit-appearance:none;appearance:none;width:14px;height:14px;
    border-radius:50%;background:#fff;border:.5px solid rgba(0,0,0,.12);box-shadow:0 1px 3px rgba(0,0,0,.2)}
  .twk-seg{position:relative;display:flex;padding:2px;border-radius:8px;background:rgba(0,0,0,.06);
    user-select:none}
  .twk-seg-thumb{position:absolute;top:2px;bottom:2px;border-radius:6px;background:rgba(255,255,255,.9);
    box-shadow:0 1px 2px rgba(0,0,0,.12);transition:left .15s cubic-bezier(.3,.7,.4,1),width .15s}
  .twk-seg.dragging .twk-seg-thumb{transition:none}
  .twk-seg button{appearance:none;position:relative;z-index:1;flex:1;border:0;background:transparent;
    color:inherit;font:inherit;font-weight:500;min-height:22px;border-radius:6px;cursor:pointer;
    padding:4px 6px;line-height:1.2;overflow-wrap:anywhere}
  .twk-toggle{position:relative;width:32px;height:18px;border:0;border-radius:999px;
    background:rgba(0,0,0,.15);transition:background .15s;cursor:pointer;padding:0}
  .twk-toggle[data-on="1"]{background:#34c759}
  .twk-toggle i{position:absolute;top:2px;left:2px;width:14px;height:14px;border-radius:50%;
    background:#fff;box-shadow:0 1px 2px rgba(0,0,0,.25);transition:transform .15s}
  .twk-toggle[data-on="1"] i{transform:translateX(14px)}
  .twk-num{display:flex;align-items:center;box-sizing:border-box;min-width:0;height:26px;padding:0 0 0 8px;
    border:.5px solid rgba(0,0,0,.1);border-radius:7px;background:rgba(255,255,255,.6)}
  .twk-num-lbl{font-weight:500;color:rgba(41,38,27,.6);cursor:ew-resize;user-select:none;padding-right:8px}
  .twk-num input{flex:1;min-width:0;height:100%;border:0;background:transparent;font:inherit;
    font-variant-numeric:tabular-nums;text-align:right;padding:0 8px 0 0;outline:none;color:inherit}
  .twk-num-unit{padding-right:8px;color:rgba(41,38,27,.45)}
  .twk-chips{display:flex;gap:6px}
  .twk-chip{position:relative;appearance:none;flex:1;min-width:0;height:46px;padding:0;border:0;
    border-radius:6px;overflow:hidden;cursor:pointer;box-shadow:0 0 0 .5px rgba(0,0,0,.12),0 1px 2px rgba(0,0,0,.06);
    transition:transform .12s cubic-bezier(.3,.7,.4,1),box-shadow .12s}
  .twk-chip:hover{transform:translateY(-1px);box-shadow:0 0 0 .5px rgba(0,0,0,.18),0 4px 10px rgba(0,0,0,.12)}
  .twk-chip[data-on="1"]{box-shadow:0 0 0 1.5px rgba(0,0,0,.85),0 2px 6px rgba(0,0,0,.15)}
  .twk-chip>span{position:absolute;top:0;bottom:0;right:0;width:34%;display:flex;flex-direction:column;
    box-shadow:-1px 0 0 rgba(0,0,0,.1)}
  .twk-chip>span>i{flex:1;box-shadow:0 -1px 0 rgba(0,0,0,.1)}
`;

interface TweaksPanelProps {
  title?: string;
  children: ReactNode;
}

export function TweaksPanel({ title = "Tweaks", children }: TweaksPanelProps) {
  const [open, setOpen] = useState(false);
  const [offset, setOffset] = useState({ x: PANEL_PAD, y: PANEL_PAD });
  const dragRef = useRef<HTMLDivElement | null>(null);
  const offsetRef = useRef(offset);

  useEffect(() => {
    offsetRef.current = offset;
  }, [offset]);

  const commitOffset = useCallback((next: { x: number; y: number }) => {
    offsetRef.current = next;
    setOffset(next);
  }, []);

  const clampToViewport = useCallback(() => {
    const panel = dragRef.current;
    if (!panel) return;
    const maxRight = Math.max(PANEL_PAD, window.innerWidth - panel.offsetWidth - PANEL_PAD);
    const maxBottom = Math.max(PANEL_PAD, window.innerHeight - panel.offsetHeight - PANEL_PAD);
    commitOffset({
      x: Math.min(maxRight, Math.max(PANEL_PAD, offsetRef.current.x)),
      y: Math.min(maxBottom, Math.max(PANEL_PAD, offsetRef.current.y)),
    });
  }, [commitOffset]);

  useEffect(() => {
    const onMessage = (event: MessageEvent) => {
      const type = (event.data as { type?: string } | undefined)?.type;
      if (type === "__activate_edit_mode") setOpen(true);
      if (type === "__deactivate_edit_mode") setOpen(false);
    };
    window.addEventListener("message", onMessage);
    window.parent.postMessage({ type: "__edit_mode_available" }, "*");
    return () => window.removeEventListener("message", onMessage);
  }, []);

  useEffect(() => {
    if (!open) return;
    clampToViewport();
    if (typeof ResizeObserver === "undefined") {
      window.addEventListener("resize", clampToViewport);
      return () => window.removeEventListener("resize", clampToViewport);
    }
    const observer = new ResizeObserver(clampToViewport);
    observer.observe(document.documentElement);
    return () => observer.disconnect();
  }, [open, clampToViewport]);

  const dismiss = () => {
    setOpen(false);
    window.parent.postMessage({ type: "__edit_mode_dismissed" }, "*");
  };

  const onDragStart = (event: PointerEvent<HTMLDivElement>) => {
    const panel = dragRef.current;
    if (!panel) return;
    panel.setPointerCapture?.(event.pointerId);
    const rect = panel.getBoundingClientRect();
    const sx = event.clientX;
    const sy = event.clientY;
    const startRight = window.innerWidth - rect.right;
    const startBottom = window.innerHeight - rect.bottom;
    const move = (moveEvent: globalThis.PointerEvent) => {
      commitOffset({
        x: startRight - (moveEvent.clientX - sx),
        y: startBottom - (moveEvent.clientY - sy),
      });
      clampToViewport();
    };
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  };

  return (
    <>
      <style>{TWEAKS_STYLE}</style>
      {!open && (
        <button className="twk-launch" type="button" onClick={() => setOpen(true)}>
          Tweaks · 方案探索
        </button>
      )}
      {open && (
        <div
          ref={dragRef}
          className="twk-panel"
          style={{ right: offset.x, bottom: offset.y } as CSSProperties}
        >
          <div className="twk-hd" onPointerDown={onDragStart}>
            <b>{title}</b>
            <button
              className="twk-x"
              aria-label="Close tweaks"
              type="button"
              onPointerDown={(event) => event.stopPropagation()}
              onClick={dismiss}
            >
              x
            </button>
          </div>
          <div className="twk-body">{children}</div>
        </div>
      )}
    </>
  );
}

export function TweakSection({ label }: { label: string }) {
  return <div className="twk-sect">{label}</div>;
}

function TweakRow({ label, value, children, inline = false }: { label: string; value?: ReactNode; children: ReactNode; inline?: boolean }) {
  return (
    <div className={inline ? "twk-row twk-row-h" : "twk-row"}>
      <div className="twk-lbl">
        <span>{label}</span>
        {value != null && <span className="twk-val">{value}</span>}
      </div>
      {children}
    </div>
  );
}

export function TweakSelect<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: Array<{ value: T; label: string }>;
  onChange: (value: T) => void;
}) {
  return (
    <TweakRow label={label}>
      <select className="twk-field" value={value} onChange={(event) => onChange(event.target.value as T)}>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </TweakRow>
  );
}

export function TweakRadio<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: Array<{ value: T; label: string }>;
  onChange: (value: T) => void;
}) {
  const trackRef = useRef<HTMLDivElement | null>(null);
  const valueRef = useRef(value);
  const [dragging, setDragging] = useState(false);

  useEffect(() => {
    valueRef.current = value;
  }, [value]);

  const maxLabel = options.reduce((max, option) => Math.max(max, option.label.length), 0);
  const fitsAsSegments = maxLabel <= ({ 2: 16, 3: 10 }[options.length] ?? 0);
  if (!fitsAsSegments) {
    return <TweakSelect label={label} value={value} options={options} onChange={onChange} />;
  }

  const idx = Math.max(0, options.findIndex((option) => option.value === value));
  const segAt = (clientX: number): T => {
    const rect = trackRef.current?.getBoundingClientRect();
    if (!rect) return valueRef.current;
    const inner = rect.width - 4;
    const index = Math.floor(((clientX - rect.left - 2) / inner) * options.length);
    return options[Math.max(0, Math.min(options.length - 1, index))].value;
  };

  const onPointerDown = (event: PointerEvent<HTMLDivElement>) => {
    setDragging(true);
    const initial = segAt(event.clientX);
    if (initial !== valueRef.current) {
      valueRef.current = initial;
      onChange(initial);
    }
    const move = (moveEvent: globalThis.PointerEvent) => {
      const next = segAt(moveEvent.clientX);
      if (next !== valueRef.current) {
        valueRef.current = next;
        onChange(next);
      }
    };
    const up = () => {
      setDragging(false);
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  };

  return (
    <TweakRow label={label}>
      <div ref={trackRef} role="radiogroup" onPointerDown={onPointerDown} className={dragging ? "twk-seg dragging" : "twk-seg"}>
        <div
          className="twk-seg-thumb"
          style={{
            left: `calc(2px + ${idx} * (100% - 4px) / ${options.length})`,
            width: `calc((100% - 4px) / ${options.length})`,
          }}
        />
        {options.map((option) => (
          <button key={option.value} type="button" role="radio" aria-checked={option.value === value}>
            {option.label}
          </button>
        ))}
      </div>
    </TweakRow>
  );
}

export function TweakToggle({ label, value, onChange }: { label: string; value: boolean; onChange: (value: boolean) => void }) {
  return (
    <div className="twk-row twk-row-h">
      <div className="twk-lbl"><span>{label}</span></div>
      <button type="button" className="twk-toggle" data-on={value ? "1" : "0"} role="switch" aria-checked={value} onClick={() => onChange(!value)}>
        <i />
      </button>
    </div>
  );
}

export function TweakNumber({
  label,
  value,
  min,
  max,
  step = 1,
  unit = "",
  onChange,
}: {
  label: string;
  value: number;
  min?: number;
  max?: number;
  step?: number;
  unit?: string;
  onChange: (value: number) => void;
}) {
  const clamp = (number: number) => Math.min(max ?? number, Math.max(min ?? number, number));
  return (
    <div className="twk-num">
      <span className="twk-num-lbl">{label}</span>
      <input type="number" value={value} min={min} max={max} step={step} onChange={(event) => onChange(clamp(Number(event.target.value)))} />
      {unit && <span className="twk-num-unit">{unit}</span>}
    </div>
  );
}

function isLight(hex: string): boolean {
  const normalized = hex.replace("#", "").padEnd(6, "0").slice(0, 6);
  const parsed = Number.parseInt(normalized, 16);
  if (Number.isNaN(parsed)) return true;
  const red = (parsed >> 16) & 255;
  const green = (parsed >> 8) & 255;
  const blue = parsed & 255;
  return red * 299 + green * 587 + blue * 114 > 148000;
}

export function TweakColor({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string | string[];
  options: Array<string | string[]>;
  onChange: (value: string | string[]) => void;
}) {
  const current = JSON.stringify(value).toLowerCase();
  return (
    <TweakRow label={label}>
      <div className="twk-chips" role="radiogroup">
        {options.map((option, index) => {
          const colors = Array.isArray(option) ? option : [option];
          const [hero, ...rest] = colors;
          const selected = JSON.stringify(option).toLowerCase() === current;
          return (
            <button
              key={`${hero}-${index}`}
              type="button"
              className="twk-chip"
              role="radio"
              aria-checked={selected}
              data-on={selected ? "1" : "0"}
              aria-label={colors.join(", ")}
              title={colors.join(" · ")}
              style={{ background: hero }}
              onClick={() => onChange(option)}
            >
              {rest.length > 0 && <span>{rest.slice(0, 4).map((color) => <i key={color} style={{ background: color }} />)}</span>}
              {selected && (
                <svg viewBox="0 0 14 14" aria-hidden="true" style={{ position: "absolute", top: 6, left: 6, width: 13, height: 13 }}>
                  <path d="M3 7.2 5.8 10 11 4.2" fill="none" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" stroke={isLight(hero) ? "rgba(0,0,0,.78)" : "#fff"} />
                </svg>
              )}
            </button>
          );
        })}
      </div>
    </TweakRow>
  );
}
