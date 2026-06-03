import React, { useState, useEffect, useMemo, useRef } from "react";

/* =====================================================================
   BJT 测试台 — Apple 原生风格 · React 组件化版本
   ---------------------------------------------------------------------
   组件结构(可按注释拆成多文件):
     App
     ├─ TitleBar
     ├─ Sidebar
     │   ├─ ConnectionGroup
     │   ├─ HardwareConfig
     │   └─ Operations
     ├─ MainContent
     │   ├─ PageHeader
     │   ├─ OutputChart
     │   ├─ Metrics
     │   ├─ TestPoints
     │   └─ LogPanel
     ├─ AIPanel
     └─ StatusBar
   复用控件:Segmented / Switch / StatusDot / ListRow / Card / Icon
   设计令牌:全部走 CSS 变量(浅色 + 深色),见底部 <Styles/>
   ===================================================================== */

/* ----------------------------- 图标 ----------------------------- */
const Icon = {
  Sun: (p) => (<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" {...p}><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></svg>),
  Moon: (p) => (<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" /></svg>),
  Chevron: (p) => (<svg className="chev" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" {...p}><path d="M6 9l6 6 6-6" /></svg>),
  Check: (p) => (<svg className="check" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" {...p}><path d="M5 13l4 4L19 7" /></svg>),
  Chart: (p) => (<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" {...p}><path d="M3 3v18h18" /><path d="M19 9l-5 5-4-4-3 3" /></svg>),
  Stop: (p) => (<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" {...p}><rect x="6" y="6" width="12" height="12" rx="2" /></svg>),
};

/* ------------------------- 可复用控件 ------------------------- */
function Segmented({ options, value, onChange, style }) {
  return (
    <div className="seg" style={style}>
      {options.map((o, i) => (
        <button key={o} className={i === value ? "on" : ""} onClick={() => onChange?.(i)}>{o}</button>
      ))}
    </div>
  );
}

function Switch({ checked, onChange }) {
  return (
    <span className="switch">
      <input type="checkbox" checked={checked} onChange={(e) => onChange?.(e.target.checked)} />
      <span className="track" /><span className="knob" />
    </span>
  );
}

function StatusDot({ on, small }) {
  return <span className={"dot" + (on ? " on" : "")} style={small ? { width: 7, height: 7, boxShadow: "none" } : undefined} />;
}

function Card({ title, meta, action, children, className = "", style }) {
  return (
    <div className={"card " + className} style={style}>
      {(title || action) && (
        <div className="card-h">
          {title && <h3>{title}</h3>}
          {meta && <span className="meta">{meta}</span>}
          {action}
        </div>
      )}
      {children}
    </div>
  );
}

/* 分组内嵌列表(macOS 设置风格) */
function List({ children, style }) { return <div className="list" style={style}>{children}</div>; }
function InputRow({ label, value, unit, onChange }) {
  return (
    <div className="row input">
      <span className="lbl">{label}</span>
      <span className="val"><input value={value} onChange={(e) => onChange?.(e.target.value)} />{unit && <span className="unit">{unit}</span>}</span>
    </div>
  );
}
function SelectRow({ label, value, options, onChange }) {
  return (
    <div className="row select">
      <span className="lbl">{label}</span>
      <span className="val">
        {options?.length ? (
          <select value={value} onChange={(e) => onChange?.(e.target.value)} aria-label={label}>
            {options.map((option) => {
              const item = typeof option === "string" ? { label: option, value: option } : option;
              return <option key={item.value} value={item.value}>{item.label}</option>;
            })}
          </select>
        ) : value}
        <Icon.Chevron />
      </span>
    </div>
  );
}

/* ============================== 标题栏 ============================== */
function TitleBar({ theme, onToggleTheme }) {
  return (
    <div className="titlebar">
      <div className="traffic"><i className="c" /><i className="y" /><i className="g" /></div>
      <h1>BJT 测试台</h1>
      <div className="right">
        <button className="theme-btn" onClick={onToggleTheme} title="切换外观">
          {theme === "dark" ? <Icon.Sun /> : <Icon.Moon />}
        </button>
      </div>
    </div>
  );
}

/* ============================== 侧栏 ============================== */
const DEFAULT_TEST_CONFIG = {
  runMode: "hardware",
  device: "雨骤 Model S",
  rb: "22000",
  rc: "220",
  ic: "0.03",
  pw: "0.30",
  icr: "0.0005–0.02",
  vce: "2.0–4.0",
  scanMode: "software",
  detectMode: "auto",
  staticDepth: "standard",
  testGoal: "full",
};

const CONNECTION_TEXT = {
  idle: "未检查",
  checking: "检查中",
  ready: "设备可用",
  error: "连接失败",
};

const SCAN_MODE_OPTIONS = [
  { label: "软件轮询", value: "software" },
  { label: "硬件触发", value: "hardware" },
  { label: "单点步进", value: "single_point" },
];

const DETECT_MODE_OPTIONS = [
  { label: "自动", value: "auto" },
  { label: "NPN", value: "NPN" },
  { label: "PNP", value: "PNP" },
];

const STATIC_DEPTH_OPTIONS = [
  { label: "默认", value: "standard" },
  { label: "保守", value: "conservative" },
  { label: "精细", value: "deep" },
];

function optionLabel(options, value) {
  return options.find((option) => option.value === value)?.label || value;
}

function parseRange(value, fallback) {
  const normalized = String(value || "").replace(/[—–~～]/g, "-");
  const parts = normalized.split("-").map((part) => Number.parseFloat(part.trim())).filter(Number.isFinite);
  return parts.length >= 2 ? [parts[0], parts[1]] : fallback;
}

function toBackendConfig(config) {
  return {
    run_mode: config.runMode,
    device: config.device,
    scan_mode: config.scanMode,
    detect_mode: config.detectMode,
    static_depth: config.staticDepth,
    test_goal: config.testGoal,
    hw_config: {
      R_B: Number.parseFloat(config.rb) || 22000,
      R_C: Number.parseFloat(config.rc) || 220,
      Ic_max_A: Number.parseFloat(config.ic) || 0.03,
      Pmax_W: Number.parseFloat(config.pw) || 0.30,
      lin_ic_range: parseRange(config.icr, [0.0005, 0.02]),
      lin_vce_window: parseRange(config.vce, [2.0, 4.0]),
    },
  };
}

function ConnectionGroup({ connectionStatus, config, onConfigChange, onConnect, onDisconnect }) {
  const mode = config.runMode === "hardware" ? 1 : 0;
  const ready = connectionStatus === "ready";
  const setMode = (nextMode) => {
    onConfigChange({
      runMode: nextMode === 1 ? "hardware" : "simulation",
      device: nextMode === 1 ? "雨骤 Model S" : "仿真后端",
    });
  };
  return (
    <div className="group">
      <div className="group-title">连接</div>
      <Segmented options={["仿真", "硬件"]} value={mode} onChange={setMode} style={{ marginBottom: 10 }} />
      <List>
        <SelectRow
          label="设备"
          value={config.device}
          options={["仿真后端", "雨骤 Model S"]}
          onChange={(device) => onConfigChange({ device, runMode: device === "仿真后端" ? "simulation" : "hardware" })}
        />
        <div className="row">
          <span className="lbl">状态</span>
          <span className="val"><span className="status"><StatusDot on={ready} />{CONNECTION_TEXT[connectionStatus] || "未检查"}</span></span>
        </div>
      </List>
      <div className="btns">
        <button className="btn primary" onClick={onConnect} disabled={connectionStatus === "checking"}>{connectionStatus === "checking" ? "检查中" : "检测设备"}</button>
        <button className="btn plain" onClick={onDisconnect}>清除状态</button>
      </div>
    </div>
  );
}

function HardwareConfig({ config, onConfigChange }) {
  const set = (k) => (v) => onConfigChange({ [k]: v });
  return (
    <div className="group">
      <div className="group-title">硬件配置</div>
      <List>
        <InputRow label="基极电阻" value={config.rb} unit="Ω" onChange={set("rb")} />
        <InputRow label="集电极电阻" value={config.rc} unit="Ω" onChange={set("rc")} />
        <InputRow label="Ic 上限" value={config.ic} unit="A" onChange={set("ic")} />
        <InputRow label="功耗上限" value={config.pw} unit="W" onChange={set("pw")} />
        <InputRow label="线性 Ic 范围" value={config.icr} unit="A" onChange={set("icr")} />
        <InputRow label="线性 Vce 窗口" value={config.vce} unit="V" onChange={set("vce")} />
        <SelectRow
          label="扫描模式"
          value={config.scanMode}
          options={SCAN_MODE_OPTIONS}
          onChange={(scanMode) => onConfigChange({ scanMode })}
        />
      </List>
    </div>
  );
}

const TEST_MODES = [
  { label: "测 Vce(sat)", value: "vce_sat", ico: "V", color: "#5856D6" },
  { label: "β 线性度", value: "beta", ico: "β", color: "#FF9500" },
  { label: "扫描曲线", value: "curves", ico: "∿", color: "#34C759" },
  { label: "完整测试", value: "full", ico: "✓", color: "var(--blue)" },
];

function Operations({ config, busy, onConfigChange, onRunAction, onEStop }) {
  const sel = Math.max(0, TEST_MODES.findIndex((mode) => mode.value === config.testGoal));
  return (
    <div className="group">
      <div className="group-title">操作</div>
      <List style={{ marginBottom: 10 }}>
        <SelectRow
          label="识别类型"
          value={config.detectMode}
          options={DETECT_MODE_OPTIONS}
          onChange={(detectMode) => onConfigChange({ detectMode })}
        />
        <SelectRow
          label="静态点"
          value={config.staticDepth}
          options={STATIC_DEPTH_OPTIONS}
          onChange={(staticDepth) => onConfigChange({ staticDepth })}
        />
      </List>
      <div className="group-title" style={{ fontSize: 11, paddingBottom: 6 }}>测试模式</div>
      <List>
        {TEST_MODES.map((m, i) => (
          <div key={m.label} className={"row opt" + (i === sel ? " sel" : "")} onClick={() => onConfigChange({ testGoal: m.value })}>
            <span className="ico" style={{ background: m.color }}>{m.ico}</span>
            <span className="lbl">{m.label}</span>
            <Icon.Check />
          </div>
        ))}
      </List>
      <div className="op-actions">
        <button className="btn primary" onClick={() => onRunAction("selected")} disabled={busy}>
          {busy ? "执行中" : "执行所选"}
        </button>
        <button className="btn plain" onClick={() => onRunAction("detect")} disabled={busy}>识别管型</button>
      </div>
      <div className="op-actions">
        <button className="btn plain" onClick={() => onRunAction("selftest")} disabled={busy}>硬件自检</button>
        <button className="btn plain" onClick={() => onRunAction("scope_check")} disabled={busy}>示波器检查</button>
      </div>
      <button className="btn danger" onClick={onEStop}><Icon.Stop style={{ verticalAlign: -2, marginRight: 4 }} />紧急停止</button>
    </div>
  );
}

function Sidebar(props) {
  return (
    <aside className="sidebar stagger">
      <ConnectionGroup {...props} />
      <HardwareConfig config={props.config} onConfigChange={props.onConfigChange} />
      <Operations config={props.config} busy={props.busy} onConfigChange={props.onConfigChange} onRunAction={props.onRunAction} onEStop={props.onEStop} />
    </aside>
  );
}

/* ============================== 主区 ============================== */
function PageHeader({ config, onConfigChange }) {
  const hw = config.runMode === "hardware";
  return (
    <div className="page-head">
      <div>
        <h2>BJT 测试台</h2>
        <div className="sub">{config.device} · {optionLabel(DETECT_MODE_OPTIONS, config.detectMode)} 双极结型三极管</div>
      </div>
      <label className="mode-toggle">
        仿真 / 硬件
        <Switch
          checked={hw}
          onChange={(checked) => onConfigChange({
            runMode: checked ? "hardware" : "simulation",
            device: checked ? "雨骤 Model S" : "仿真后端",
          })}
        />
      </label>
    </div>
  );
}

/* Ic-Vce 输出特性图(SVG) */
function OutputChart({ measurements }) {
  const W = 720, H = 320, ml = 56, mr = 24, mt = 16, mb = 44;
  const plotW = W - ml - mr, plotH = H - mt - mb;
  const VCE_MAX = 5;
  const xs = (v) => ml + (v / VCE_MAX) * plotW;
  const plottedPoints = useMemo(
    () => measurements
      .map((point) => ({
        vbb: Number(point.vbb),
        vce: Number(point.vce),
        ic: Number(point.ic),
      }))
      .filter((point) => Number.isFinite(point.vce) && Number.isFinite(point.ic)),
    [measurements],
  );
  const curveGroups = useMemo(() => {
    const grouped = new Map();
    plottedPoints.forEach((point, index) => {
      const key = Number.isFinite(point.vbb) ? point.vbb.toFixed(3) : `group-${index}`;
      if (!grouped.has(key)) {
        grouped.set(key, {
          label: Number.isFinite(point.vbb) ? `Vbb ${point.vbb.toFixed(2)}V` : "未分组",
          points: [],
        });
      }
      grouped.get(key).points.push(point);
    });
    return Array.from(grouped.values()).map((group) => ({
      ...group,
      points: group.points.slice().sort((a, b) => a.vce - b.vce),
    }));
  }, [plottedPoints]);
  const yAxis = useMemo(() => {
    const maxIcMilli = plottedPoints.reduce((currentMax, point) => Math.max(currentMax, Math.abs(point.ic)), 0);
    const defaultAxis = {
      unit: "mA",
      convert: (value) => value,
      max: 25,
      decimals: 0,
    };
    if (maxIcMilli <= 0) return defaultAxis;

    const unitConfig = maxIcMilli >= 1000
      ? {
        unit: "A",
        convert: (value) => value / 1000,
      }
      : maxIcMilli < 1
        ? {
          unit: "µA",
          convert: (value) => value * 1000,
        }
        : {
          unit: "mA",
          convert: (value) => value,
        };

    const maxDisplay = unitConfig.convert(maxIcMilli);
    const niceAxisMax = (value) => {
      if (value <= 0) return 1;
      const exponent = Math.floor(Math.log10(value));
      const base = 10 ** exponent;
      const normalized = value / base;
      const niceNormalized = normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10;
      return niceNormalized * base;
    };

    return {
      ...unitConfig,
      max: niceAxisMax(maxDisplay),
      decimals: maxDisplay < 1 ? 2 : maxDisplay < 10 ? 1 : 0,
    };
  }, [plottedPoints]);
  const ys = (displayIc) => mt + plotH - (displayIc / yAxis.max) * plotH;

  const grid = useMemo(() => {
    const els = [];
    for (let i = 0; i <= 5; i++) {
      const x = xs(i);
      els.push(<line key={"vg" + i} className="grid" x1={x} y1={mt} x2={x} y2={mt + plotH} />);
      els.push(<text key={"vt" + i} className="tick" x={x} y={mt + plotH + 18} textAnchor="middle">{i}</text>);
    }
    for (let i = 0; i <= 5; i++) {
      const ic = (i / 5) * yAxis.max;
      const y = ys(ic);
      els.push(<line key={"hg" + i} className="grid" x1={ml} y1={y} x2={ml + plotW} y2={y} />);
      els.push(<text key={"ht" + i} className="tick" x={ml - 10} y={y + 4} textAnchor="end">{ic.toFixed(yAxis.decimals)}</text>);
    }
    return els;
  }, [mt, plotH, ml, plotW, yAxis]);

  return (
    <Card className={"chart-card section" + (plottedPoints.length > 0 ? " connected" : "")} title="Ic-Vce 输出特性"
      meta={plottedPoints.length > 0 ? `${curveGroups.length} 条曲线 / ${plottedPoints.length} 个采样点` : "等待真实测量"}>
      <div className="chart-wrap">
        <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ display: "block" }}>
          {grid}
          <line className="axis" x1={ml} y1={mt} x2={ml} y2={mt + plotH} />
          <line className="axis" x1={ml} y1={mt + plotH} x2={ml + plotW} y2={mt + plotH} />
          <text className="axt" x={ml + plotW / 2} y={H - 8} textAnchor="middle">Vce (V)</text>
          <text className="axt" transform={`translate(16,${mt + plotH / 2}) rotate(-90)`} textAnchor="middle">{`Ic (${yAxis.unit})`}</text>
          {curveGroups.map((group, index) => {
            if (group.points.length < 2) return null;
            const d = group.points.map((point, pointIndex) => {
              const displayIc = yAxis.convert(Math.abs(point.ic));
              return `${pointIndex === 0 ? "M" : "L"} ${xs(Math.max(0, Math.min(VCE_MAX, Math.abs(point.vce))))} ${ys(Math.max(0, Math.min(yAxis.max, displayIc)))}`;
            }).join(" ");
            const lastPoint = group.points[group.points.length - 1];
            const lastDisplayIc = yAxis.convert(Math.abs(lastPoint.ic));
            const lastX = xs(Math.max(0, Math.min(VCE_MAX, Math.abs(lastPoint.vce))));
            const labelNearEdge = lastX > ml + plotW - 72;
            const labelOffsetY = index % 2 === 0 ? -8 : 12;
            return (
              <g key={`curve-${group.label}-${index}`}>
                <path className="curve" d={d} />
                <text
                  className="clabel"
                  x={lastX + (labelNearEdge ? -8 : 8)}
                  y={ys(Math.max(0, Math.min(yAxis.max, lastDisplayIc))) + labelOffsetY}
                  textAnchor={labelNearEdge ? "end" : "start"}
                >
                  {group.label}
                </text>
              </g>
            );
          })}
          {plottedPoints.map((point, index) => (
            <circle
              key={index}
              className="sample-dot"
              cx={xs(Math.max(0, Math.min(VCE_MAX, Math.abs(point.vce))))}
              cy={ys(Math.max(0, Math.min(yAxis.max, yAxis.convert(Math.abs(point.ic)))))}
              r="4"
            />
          ))}
        </svg>
        <div className="chart-empty">
          <div className="pulse"><Icon.Chart /></div>
          <span>等待测量数据</span>
          <span className="hint">设备探测不会生成曲线；执行扫描后才显示数据</span>
        </div>
      </div>
    </Card>
  );
}

const METRIC_DEFS = [
  { key: "vbe", label: "基射电压", sub: "Vbe", val: "0.68", unit: "V" },
  { key: "ib", label: "基极电流", sub: "Ib", val: "45", unit: "µA" },
  { key: "vce", label: "集射电压", sub: "Vce", val: "3.20", unit: "V" },
  { key: "ic", label: "集电极电流", sub: "Ic", val: "8.9", unit: "mA" },
  { key: "beta", label: "电流增益", sub: "β", val: "198", unit: "" },
  { key: "region", label: "工作区状态", sub: "", val: "放大区", unit: "" },
];

function Metrics({ latestPoint }) {
  return (
    <div className="section">
      <div className="card-h" style={{ marginBottom: 12 }}><h3>实时数值</h3></div>
      <div className="metrics">
        {METRIC_DEFS.map((m) => (
          <div className="metric" key={m.key}>
            <div className="k">{m.label}{m.sub && <b>{m.sub}</b>}</div>
            {!latestPoint ? (
              <div className="v idle" style={m.key === "region" ? { fontSize: 16 } : undefined}>—</div>
            ) : m.key === "region" ? (
              <div className="v" style={{ fontSize: 16 }}>
                <span className="region"><StatusDot on small />{latestPoint.region}</span>
              </div>
            ) : (
              <div className="v">{latestPoint[m.key] ?? m.val}{m.unit && <small>{m.unit}</small>}</div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function TestPoints({ plan, points, limits, busy, onPointChange, onAddPoint, onRemovePoint, onLimitChange, onApplyPlan, onExecutePlan }) {
  return (
    <Card title="测试点" action={
      <div className="tp-actions">
        <button className="chip go" onClick={onApplyPlan} disabled={!plan}>应用到计划</button>
        <button className="chip" onClick={onAddPoint}>添加点</button>
        <button className="chip" onClick={onRemovePoint} disabled={points.length === 0}>删除点</button>
        <button className="chip run" onClick={onExecutePlan} disabled={!plan || busy}>{busy ? "执行中" : "执行计划"}</button>
      </div>}>
      <div className="tp-inputs">
        <div className="field"><label>Ic 上限 (A)</label><input className="inp" value={limits.ic} onChange={(e) => onLimitChange("ic", e.target.value)} /></div>
        <div className="field"><label>功耗 (W)</label><input className="inp" value={limits.power} onChange={(e) => onLimitChange("power", e.target.value)} /></div>
      </div>
      <div className="tp-table">
        <div className="th"><span>Vcc (V)</span><span>Vbb (V)</span><span>来源</span></div>
        {points.length === 0 ? (
          <div><div className="empty-mini">尚未生成或添加测试点</div></div>
        ) : points.map((point, index) => (
          <div className="tp-row" key={index}>
            <input value={point.vcc} onChange={(e) => onPointChange(index, "vcc", e.target.value)} />
            <input value={point.vbb} onChange={(e) => onPointChange(index, "vbb", e.target.value)} />
            <span>{plan ? plan.model : "手动"}</span>
          </div>
        ))}
      </div>
    </Card>
  );
}

function LogPanel({ logs, onClear }) {
  const boxRef = useRef(null);
  useEffect(() => { if (boxRef.current) boxRef.current.scrollTop = boxRef.current.scrollHeight; }, [logs]);
  return (
    <Card title="日志" meta={`${logs.length} 条`}>
      <div className="log-box" ref={boxRef}>
        {logs.length === 0
          ? <div className="log-empty">暂无事件</div>
          : logs.map((l, i) => <div className="ln" key={i}><span className="t">{l.t}</span><span>{l.m}</span></div>)}
      </div>
      <div className="log-foot"><button className="chip" style={{ width: "100%" }} onClick={onClear}>清空日志</button></div>
    </Card>
  );
}

function MainContent({
  measurements,
  latestPoint,
  logs,
  config,
  currentPlan,
  testPoints,
  planLimits,
  onConfigChange,
  onPointChange,
  onAddPoint,
  onRemovePoint,
  onLimitChange,
  onApplyPlan,
  onExecutePlan,
  busy,
  onClearLog,
}) {
  return (
    <main className="content">
      <PageHeader config={config} onConfigChange={onConfigChange} />
      <OutputChart measurements={measurements} />
      <Metrics latestPoint={latestPoint} />
      <div className="two-col">
        <TestPoints
          plan={currentPlan}
          points={testPoints}
          limits={planLimits}
          busy={busy}
          onPointChange={onPointChange}
          onAddPoint={onAddPoint}
          onRemovePoint={onRemovePoint}
          onLimitChange={onLimitChange}
          onApplyPlan={onApplyPlan}
          onExecutePlan={onExecutePlan}
        />
        <LogPanel logs={logs} onClear={onClearLog} />
      </div>
    </main>
  );
}

/* ============================== AI 面板 ============================== */
const INTRO = (
  <div className="intro">
    <b>从这里开始,读懂晶体管测试的一切</b>
    你可以让 AI 生成测试计划、修改扫描范围、解释结果,或把计划交给仿真 / 硬件执行。
  </div>
);

const PROFILE_FIELD_LABELS = {
  bjt_type: "管型",
  vceo_max_v: "Vceo",
  ic_max_a: "Ic",
  p_tot_w: "Ptot",
};

const PROFILE_UNSAVED_MESSAGE = "BJTagent：本次型号尚未保存到本地库，可在确认后写入型号库";
const PROFILE_SAVED_MESSAGE = "BJTagent：已保存到本地型号库，后续可直接复用";
const LIBRARY_PANEL_OPTIONS = ["BJTagent", "器件库"];
const LIBRARY_COMMAND_HINTS = ["列出已保存型号", "查看 ", "删除 ", "启用 ", "禁用 ", "更新 ", "新增 "];
const HARDWARE_WARNING_DETAIL = "存在误接线、器件损坏或过流风险。请确认器件、夹具、引脚、限流电阻、量程和供电状态已经检查。";

function formatProfileFieldValue(key, value) {
  if (value === undefined || value === null || value === "") return null;
  if (key === "vceo_max_v") return `Vceo ${value}V`;
  if (key === "ic_max_a") return `Ic ${Number(value) * 1000}mA`;
  if (key === "p_tot_w") return `Ptot ${Number(value) * 1000}mW`;
  return String(value).toUpperCase();
}

function looksLikeUnsavedProfileResponse(text) {
  return text.includes("尚未保存到本地型号库")
    && (text.includes("保存这个型号") || text.includes("写入库"));
}

function looksLikeSavedProfileResponse(text) {
  return (text.includes("已将") && text.includes("写入本地型号库"))
    || text.includes("已更新")
    || text.includes("后续再次测试该型号时，会优先使用本地已确认参数");
}

function resolveProfileModel(conversationState, currentPlan) {
  const candidateProfileModel = conversationState?.candidate_profile?.model || "";
  const pendingProfileModel = conversationState?.pending_profile_model || "";
  return candidateProfileModel || pendingProfileModel || currentPlan?.model || "";
}

function looksLikeLibraryCommand(text) {
  return LIBRARY_COMMAND_HINTS.some((item) => text.includes(item));
}

function AIPanel({
  config,
  currentPlan,
  testPoints,
  planLimits,
  measurements,
  logs,
  conversationState,
  setConversationState,
  msgs,
  setMsgs,
  tab,
  setTab,
  provider,
  setProvider,
  model,
  setModel,
  apiKey,
  setApiKey,
  text,
  setText,
  agentStatus,
  agentEvent,
  onPlanReady,
  rightPanel,
  setRightPanel,
  onOpenLibrary,
}) {
  const [apiOnline, setApiOnline] = useState(false);
  const chatRef = useRef(null);
  const lastPendingModelRef = useRef("");
  const lastFieldSignatureRef = useRef("");
  const lastAgentEventIdRef = useRef(null);
  const lastSystemMessageKeyRef = useRef("");
  const unsavedProfileNoticeRef = useRef(new Set());
  const savedProfileNoticeRef = useRef(new Set());
  const pendingProfileModel = conversationState?.pending_profile_model || "";
  const pendingProfileFields = conversationState?.pending_profile_fields || {};
  const profileFieldOrder = ["bjt_type", "vceo_max_v", "ic_max_a", "p_tot_w"];
  const recordedFields = profileFieldOrder
    .map((key) => formatProfileFieldValue(key, pendingProfileFields[key]))
    .filter(Boolean);
  const missingFields = profileFieldOrder
    .filter((key) => !formatProfileFieldValue(key, pendingProfileFields[key]))
    .map((key) => PROFILE_FIELD_LABELS[key] || key);
  const addAgentMessage = (message) =>
    setMsgs((m) => [...m, { role: "system", text: message }]);
  const pushUniqueSystemMessage = (message, dedupeKey = message) => {
    if (lastSystemMessageKeyRef.current === dedupeKey) return;
    lastSystemMessageKeyRef.current = dedupeKey;
    addAgentMessage(message);
  };
  useEffect(() => { if (chatRef.current) chatRef.current.scrollTop = chatRef.current.scrollHeight; }, [msgs]);
  useEffect(() => {
    if (!pendingProfileModel || lastPendingModelRef.current === pendingProfileModel) return;
    lastPendingModelRef.current = pendingProfileModel;
    pushUniqueSystemMessage("BJTagent：识别到未知型号，进入规格补全流程", `pending-profile:${pendingProfileModel}`);
  }, [pendingProfileModel]);
  useEffect(() => {
    const signature = JSON.stringify(pendingProfileFields);
    if (!pendingProfileModel || signature === lastFieldSignatureRef.current) return;
    lastFieldSignatureRef.current = signature;
    const fieldCount = Object.keys(pendingProfileFields).length;
    if (fieldCount > 0 && missingFields.length > 0) {
      pushUniqueSystemMessage("BJTagent：已记录规格字段，继续等待缺失信息", `pending-fields:${signature}:missing`);
    }
    if (fieldCount >= profileFieldOrder.length) {
      pushUniqueSystemMessage("BJTagent：规格已完整，可生成保守计划", `pending-fields:${signature}:complete`);
    }
  }, [pendingProfileModel, pendingProfileFields, missingFields.length]);
  useEffect(() => {
    if (!agentEvent?.id || agentEvent.id === lastAgentEventIdRef.current) return;
    lastAgentEventIdRef.current = agentEvent.id;
    pushUniqueSystemMessage(agentEvent.text, `agent-event:${agentEvent.text}`);
  }, [agentEvent]);

  const checkApi = async () => {
    try {
      const res = await fetch("http://127.0.0.1:8765/api/health");
      const data = await res.json();
      setApiOnline(Boolean(res.ok && data.ok));
    } catch {
      setApiOnline(false);
    }
  };
  useEffect(() => { checkApi(); }, []);

  const send = async () => {
    const q = text.trim() || "帮我为 2N2222 生成完整测试计划";
    setMsgs((m) => [...m, { role: "me", text: q }]);
    setText("");
    if (looksLikeLibraryCommand(q)) {
      onOpenLibrary?.(q);
    }
    const backendConfig = toBackendConfig(config);
    const contextPlan = currentPlan ? {
      ...currentPlan,
      static_points: testPoints
        .map((point) => ({ vcc: Number.parseFloat(point.vcc), vbb: Number.parseFloat(point.vbb) }))
        .filter((point) => Number.isFinite(point.vcc) && Number.isFinite(point.vbb)),
      ic_limit_a: Number.parseFloat(planLimits.ic) || currentPlan.ic_limit_a,
      power_limit_w: Number.parseFloat(planLimits.power) || currentPlan.power_limit_w,
    } : null;
    try {
      const res = await fetch("http://127.0.0.1:8765/api/ai-chat", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          text: q,
          mode: config.runMode,
          config: backendConfig,
          context: {
            current_plan: contextPlan,
            conversation_state: conversationState,
            measurements,
            logs: logs.map((item) => `${item.t} ${item.m}`),
            messages: msgs.map((item) => ({ role: item.role === "me" ? "user" : "assistant", content: item.text })),
          },
          ai_settings: {
            provider: provider === 1 ? "deepseek" : "local",
            model,
            api_key: apiKey,
          },
        }),
      });
      const data = await res.json();
      if (!res.ok || !data.ok) throw new Error(data.error || "API unavailable");
      setApiOnline(true);
      if (looksLikeLibraryCommand(q) || data.intent === "manage_profile_library") {
        onOpenLibrary?.(q);
      }
      const resolvedProfileModel = resolveProfileModel(data.conversation_state || null, currentPlan);
      setConversationState(data.conversation_state || null);
      if (data.plan) onPlanReady?.(data.plan);
      setMsgs((m) => [...m, { role: "ai", text: data.response }]);
      if (resolvedProfileModel && looksLikeUnsavedProfileResponse(data.response)) {
        if (!unsavedProfileNoticeRef.current.has(resolvedProfileModel) && !savedProfileNoticeRef.current.has(resolvedProfileModel)) {
          unsavedProfileNoticeRef.current.add(resolvedProfileModel);
          addAgentMessage(PROFILE_UNSAVED_MESSAGE);
        }
      }
      if (resolvedProfileModel && looksLikeSavedProfileResponse(data.response)) {
        unsavedProfileNoticeRef.current.delete(resolvedProfileModel);
        if (!savedProfileNoticeRef.current.has(resolvedProfileModel)) {
          savedProfileNoticeRef.current.add(resolvedProfileModel);
          addAgentMessage(PROFILE_SAVED_MESSAGE);
        }
      }
    } catch (error) {
      setApiOnline(false);
      setMsgs((m) => [...m, { role: "ai", text: `AI 服务不可用，未生成测试计划。请先启动后端服务；错误信息:${error.message || "连接失败"}` }]);
    }
  };

  return (
    <aside className="inspector">
      <div className="insp-head"><h3>BJTagent</h3><button className="clear" onClick={() => setMsgs([])}>清空</button></div>
      <div className="insp-tabs">
        <Segmented
          options={["BJTagent", "器件库"]}
          value={rightPanel === "BJTagent" ? 0 : 1}
          onChange={(index) => setRightPanel(index === 0 ? "BJTagent" : "器件库")}
        />
      </div>
      <div className="agent-card">
        <div className="agent-card-head">
          <strong>BJTagent</strong>
          <span className="agent-badge">{agentStatus}</span>
        </div>
        {pendingProfileModel ? (
          <>
            <div className="agent-line">当前正在补全：{pendingProfileModel}</div>
            <div className="agent-line">已记录字段：{recordedFields.length > 0 ? recordedFields.join(" / ") : "暂无"}</div>
            <div className="agent-line">缺失字段：{missingFields.length > 0 ? missingFields.join(" / ") : "无"}</div>
            <div className="agent-line">可直接回复：NPN，Vceo 40V，Ic 200mA，Ptot 500mW</div>
          </>
        ) : (
          <div className="agent-line">当前状态：{agentStatus}</div>
        )}
      </div>
      <div className="insp-tabs"><Segmented options={["测试对话", "应用配置"]} value={tab} onChange={setTab} /></div>
      <div className="chat" ref={chatRef}>
        {msgs.length === 0 ? INTRO : msgs.map((m, i) => <div key={i} className={"bubble " + m.role}>{m.text}</div>)}
      </div>
      <div className="composer">
        <button className={"service " + (apiOnline ? "on" : "off")} onClick={checkApi}>
          {apiOnline ? "AI 服务已连接" : "AI 服务未启动 · 重试"}
        </button>
        <Segmented options={["本地", "DeepSeek"]} value={provider} onChange={setProvider} />
        <input className="mini" value={model} onChange={(e) => setModel(e.target.value)} />
        <input className="mini" type="password" placeholder="API Key,仅当前进程使用" value={apiKey} onChange={(e) => setApiKey(e.target.value)} />
        <textarea placeholder="直接描述器件型号、测试目标、限制条件…" value={text} onChange={(e) => setText(e.target.value)} />
        <button className="send" onClick={send}>发送</button>
      </div>
    </aside>
  );
}

function DeviceLibraryPanel({
  rightPanel,
  setRightPanel,
  loading,
  error,
  profiles,
  selectedProfile,
  search,
  enabledOnly,
  onSearchChange,
  onEnabledOnlyChange,
  onRefresh,
  onSelectProfile,
  onCreateProfile,
  onEditProfile,
  onDeleteProfile,
  onToggleProfileEnabled,
}) {
  return (
    <aside className="inspector">
      <div className="insp-head"><h3>器件库</h3><button className="clear" onClick={onRefresh}>刷新</button></div>
      <div className="insp-tabs">
        <Segmented
          options={["BJTagent", "器件库"]}
          value={rightPanel === "BJTagent" ? 0 : 1}
          onChange={(index) => setRightPanel(index === 0 ? "BJTagent" : "器件库")}
        />
      </div>
      <div className="agent-card">
        <div className="agent-card-head">
          <strong>用户器件库</strong>
          <span className="agent-badge">{profiles.length} 条</span>
        </div>
        <div className="agent-line">搜索器件库</div>
        <input className="mini" placeholder="搜索器件库" value={search} onChange={(e) => onSearchChange(e.target.value)} />
        <label className="agent-line" style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 8 }}>
          <input type="checkbox" checked={enabledOnly} onChange={(e) => onEnabledOnlyChange(e.target.checked)} />
          仅看启用
        </label>
        <button className="send" style={{ marginTop: 8 }} onClick={onCreateProfile}>新增器件</button>
        {error ? <div className="agent-line" style={{ marginTop: 8 }}>{error}</div> : null}
      </div>
      <div className="chat">
        {loading ? <div className="bubble system">器件库加载中…</div> : null}
        {!loading && profiles.length === 0 ? <div className="bubble system">暂无器件库记录。</div> : null}
        {!loading && profiles.map((item) => (
          <button
            key={item.model}
            className={"bubble system"}
            style={{ width: "100%", textAlign: "left", cursor: "pointer" }}
            onClick={() => onSelectProfile(item.model)}
          >
            {item.model} · {item.bjt_type} · {item.enabled ? "启用" : "禁用"}
          </button>
        ))}
      </div>
      <div className="composer">
        {selectedProfile ? (
          <>
            <div className="intro">
              <b>{selectedProfile.model}</b>
              {` ${selectedProfile.bjt_type} · ${selectedProfile.enabled ? "启用" : "禁用"} · 来源 ${selectedProfile.source || "user_confirmed"}`}
              <br />
              {`Vceo ${selectedProfile.vceo_max_v}V · Ic ${Number(selectedProfile.ic_max_a || 0) * 1000}mA · Ptot ${Number(selectedProfile.p_tot_w || 0) * 1000}mW`}
            </div>
            <button className="send" onClick={() => onEditProfile(selectedProfile)}>更新器件</button>
            <button className="send" onClick={() => onToggleProfileEnabled(selectedProfile)}>
              {selectedProfile.enabled ? "禁用器件" : "启用器件"}
            </button>
            <button className="send" onClick={() => onDeleteProfile(selectedProfile)}>删除器件</button>
          </>
        ) : (
          <div className="intro"><b>器件库</b>点击列表项查看详情，或用上方“新增器件”创建记录。</div>
        )}
      </div>
    </aside>
  );
}

/* ============================== 状态栏 ============================== */
function StatusBar({ connectionStatus, deviceSerial, config }) {
  const ready = connectionStatus === "ready";
  const suffix = ready && deviceSerial ? ` · ${deviceSerial}` : "";
  return (
    <div className="statusbar"><StatusDot on={ready} />{CONNECTION_TEXT[connectionStatus] || "未检查"} · {config.device}{suffix}</div>
  );
}

/* ============================== App ============================== */
export default function App() {
  const [theme, setTheme] = useState(() =>
    typeof window !== "undefined" && window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  const [connectionStatus, setConnectionStatus] = useState("idle");
  const [deviceSerial, setDeviceSerial] = useState("");
  const [measurements, setMeasurements] = useState([]);
  const [focusMeasurement, setFocusMeasurement] = useState(null);
  const [logs, setLogs] = useState([]);
  const [config, setConfig] = useState(DEFAULT_TEST_CONFIG);
  const [currentPlan, setCurrentPlan] = useState(null);
  const [conversationState, setConversationState] = useState(null);
  const [aiMessages, setAiMessages] = useState([]);
  const [aiTab, setAiTab] = useState(0);
  const [aiProvider, setAiProvider] = useState(1);
  const [aiModel, setAiModel] = useState("deepseek-v4-flash");
  const [aiApiKey, setAiApiKey] = useState("");
  const [aiText, setAiText] = useState("");
  const [testPoints, setTestPoints] = useState([]);
  const [planLimits, setPlanLimits] = useState({ ic: DEFAULT_TEST_CONFIG.ic, power: DEFAULT_TEST_CONFIG.pw });
  const [busy, setBusy] = useState(false);
  const [agentEvent, setAgentEvent] = useState(null);
  const [rightPanel, setRightPanel] = useState("BJTagent");
  const [userProfiles, setUserProfiles] = useState([]);
  const [selectedProfile, setSelectedProfile] = useState(null);
  const [librarySearch, setLibrarySearch] = useState("");
  const [libraryEnabledOnly, setLibraryEnabledOnly] = useState(false);
  const [libraryLoading, setLibraryLoading] = useState(false);
  const [libraryError, setLibraryError] = useState("");
  const agentStatus = useMemo(() => {
    if (busy) return "执行中";
    if (conversationState?.pending_profile_model) return "等待补充未知型号规格";
    if (currentPlan && config.runMode === "hardware") return "等待硬件确认";
    if (currentPlan && config.runMode === "simulation") return "仿真可执行";
    if (currentPlan) return "已生成计划";
    return "空闲";
  }, [busy, conversationState, currentPlan, config.runMode]);

  const stamp = () => new Date().toLocaleTimeString("zh-CN", { hour12: false });
  const addLog = (m) => setLogs((l) => [...l, { t: stamp(), m }]);
  const emitAgentEvent = (text) => setAgentEvent({ id: `${Date.now()}-${Math.random()}`, text });
  const latestPoint = focusMeasurement || measurements[measurements.length - 1] || null;
  const normalizePoint = (point) => ({
    vcc: String(point?.vcc ?? "3.0"),
    vbb: String(point?.vbb ?? "2.0"),
  });
  const normalizeMeasurement = (point) => ({
    vbb: point.Vbb,
    vcc: point.Vcc,
    vbe: Number(point.Vbe).toFixed(3),
    vce: Number(point.Vce).toFixed(3),
    ib: (Number(point.Ib) * 1e6).toFixed(1),
    ic: (Number(point.Ic) * 1e3).toFixed(2),
    beta: Number(point.beta).toFixed(1),
    region: String(point.region || "unknown"),
  });
  const applyMeasurements = (items, latestMeasurement = null) => {
    const nextMeasurements = (items || []).map(normalizeMeasurement);
    setMeasurements(nextMeasurements);
    setFocusMeasurement(latestMeasurement ? normalizeMeasurement(latestMeasurement) : (nextMeasurements[nextMeasurements.length - 1] || null));
    return nextMeasurements;
  };
  const updateConfig = (patch) => {
    if ("runMode" in patch || "device" in patch) {
      setConnectionStatus("idle");
      setDeviceSerial("");
    }
    setConfig((current) => ({ ...current, ...patch }));
  };
  const handlePlanReady = (plan) => {
    setCurrentPlan(plan);
    setTestPoints((plan.static_points || []).map(normalizePoint));
    setPlanLimits({
      ic: String(plan.ic_limit_a ?? config.ic),
      power: String(plan.power_limit_w ?? config.pw),
    });
    addLog(`AI 计划已载入测试点: ${plan.model} / ${plan.goal} / ${plan.static_points?.length || 0} 个点。`);
    emitAgentEvent("BJTagent：计划已载入测试点");
    if (config.runMode === "hardware") {
      emitAgentEvent("BJTagent：当前为硬件模式，执行前仍需要确认");
    }
  };
  const changePoint = (index, key, value) => {
    setTestPoints((points) => points.map((point, i) => i === index ? { ...point, [key]: value } : point));
  };
  const addPoint = () => {
    setTestPoints((points) => {
      const last = points[points.length - 1] || { vcc: "3.0", vbb: "2.0" };
      return [...points, { vcc: last.vcc, vbb: last.vbb }];
    });
    addLog("已添加一个手动测试点。");
  };
  const removePoint = () => {
    setTestPoints((points) => points.slice(0, -1));
    addLog("已删除最后一个测试点。");
  };
  const changeLimit = (key, value) => {
    setPlanLimits((limits) => ({ ...limits, [key]: value }));
  };
  const applyPlanEdits = () => {
    if (!currentPlan) {
      addLog("当前没有 AI 计划，无法应用测试点。");
      return;
    }
    const safePoints = testPoints
      .map((point) => ({ vcc: Number.parseFloat(point.vcc), vbb: Number.parseFloat(point.vbb) }))
      .filter((point) => Number.isFinite(point.vcc) && Number.isFinite(point.vbb));
    if (safePoints.length === 0) {
      addLog("测试点无效：至少需要一个数值有效的 Vcc/Vbb。");
      return;
    }
    const nextPlan = {
      ...currentPlan,
      ic_limit_a: Number.parseFloat(planLimits.ic) || currentPlan.ic_limit_a,
      power_limit_w: Number.parseFloat(planLimits.power) || currentPlan.power_limit_w,
      static_points: safePoints,
    };
    setCurrentPlan(nextPlan);
    setTestPoints(safePoints.map(normalizePoint));
    addLog(`已应用测试点到当前计划: ${safePoints.length} 个点，Ic≤${nextPlan.ic_limit_a}A，P≤${nextPlan.power_limit_w}W。`);
    return nextPlan;
  };
  const planWithCurrentEdits = () => {
    if (!currentPlan) return null;
    const safePoints = testPoints
      .map((point) => ({ vcc: Number.parseFloat(point.vcc), vbb: Number.parseFloat(point.vbb) }))
      .filter((point) => Number.isFinite(point.vcc) && Number.isFinite(point.vbb));
    if (safePoints.length === 0) return null;
    return {
      ...currentPlan,
      mode: config.runMode,
      scan_mode: config.scanMode,
      ic_limit_a: Number.parseFloat(planLimits.ic) || currentPlan.ic_limit_a,
      power_limit_w: Number.parseFloat(planLimits.power) || currentPlan.power_limit_w,
      static_points: safePoints,
    };
  };

  const postJson = async (path, body) => {
    const res = await fetch(`http://127.0.0.1:8765${path}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error(data.error || "请求失败");
    return data;
  };
  const getJson = async (path) => {
    const res = await fetch(`http://127.0.0.1:8765${path}`);
    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error(data.error || "请求失败");
    return data;
  };
  const profileModelFromCommand = (text) => {
    const match = text.match(/\b([A-Za-z0-9-]{3,})\b/);
    return match ? match[1].toUpperCase() : "";
  };
  const loadUserProfiles = async (query = librarySearch, enabledOnly = libraryEnabledOnly) => {
    setLibraryLoading(true);
    setLibraryError("");
    try {
      const data = await getJson(`/api/user-profiles?query=${encodeURIComponent(query)}&enabled_only=${enabledOnly ? "true" : "false"}`);
      setUserProfiles(data.items || []);
    } catch (error) {
      setLibraryError(`器件库加载失败: ${error.message}`);
      setUserProfiles([]);
    } finally {
      setLibraryLoading(false);
    }
  };
  const loadUserProfileDetail = async (model) => {
    if (!model) return;
    try {
      const data = await getJson(`/api/user-profiles?model=${encodeURIComponent(model)}`);
      setSelectedProfile(data.record || null);
    } catch (error) {
      setLibraryError(`器件详情加载失败: ${error.message}`);
      setSelectedProfile(null);
    }
  };
  const openLibraryPanel = async (sourceText = "") => {
    setRightPanel("器件库");
    const model = profileModelFromCommand(sourceText);
    if (!model) {
      setSelectedProfile(null);
    }
    await loadUserProfiles(model || librarySearch, libraryEnabledOnly);
    if (model) {
      await loadUserProfileDetail(model);
    }
  };
  const promptProfilePayload = (current = null) => {
    const model = window.prompt("器件型号", current?.model || "");
    if (!model) return null;
    const bjtType = (window.prompt("管型 (NPN/PNP)", current?.bjt_type || "NPN") || "").toUpperCase();
    const vceo = window.prompt("Vceo (V)", String(current?.vceo_max_v ?? 40));
    const icMilliAmp = window.prompt("Ic 最大值 (mA)", String((Number(current?.ic_max_a ?? 0.2) * 1000)));
    const pMilliWatt = window.prompt("Ptot (mW)", String((Number(current?.p_tot_w ?? 0.5) * 1000)));
    if (!bjtType || !vceo || !icMilliAmp || !pMilliWatt) return null;
    return {
      model: model.toUpperCase(),
      bjt_type: bjtType,
      vceo_max_v: Number(vceo),
      ic_max_a: Number(icMilliAmp) / 1000,
      p_tot_w: Number(pMilliWatt) / 1000,
      notes: current?.notes || "",
      source: current?.source || "manual_edit",
      enabled: current?.enabled ?? true,
    };
  };
  const createUserProfile = async () => {
    const payload = promptProfilePayload();
    if (!payload) return;
    try {
      const data = await postJson("/api/user-profiles", payload);
      setSelectedProfile(data.record || null);
      await loadUserProfiles();
      addLog(`器件库已新增: ${payload.model}`);
      setRightPanel("器件库");
    } catch (error) {
      setLibraryError(`新增器件失败: ${error.message}`);
    }
  };
  const editUserProfile = async (profile) => {
    const payload = promptProfilePayload(profile);
    if (!payload) return;
    try {
      let data = await postJson("/api/user-profiles/update", {
        model: profile.model,
        patch: payload,
        confirm_critical: false,
      });
      if (data.status === "confirmation_required") {
        const changes = (data.critical_changes || []).map((item) => `${item.field}: ${item.old} -> ${item.new}`).join("\n");
        const ok = window.confirm(`你正在修改安全关键字段，需要二次确认：\n${changes}`);
        if (!ok) return;
        data = await postJson("/api/user-profiles/update", {
          model: profile.model,
          patch: payload,
          confirm_critical: true,
        });
      }
      setSelectedProfile(data.record || null);
      await loadUserProfiles();
      addLog(`器件库已更新: ${profile.model}`);
    } catch (error) {
      setLibraryError(`更新器件失败: ${error.message}`);
    }
  };
  const deleteUserProfile = async (profile) => {
    if (!window.confirm(`确定删除 ${profile.model} 吗？`)) return;
    try {
      await postJson("/api/user-profiles/delete", { model: profile.model });
      setSelectedProfile(null);
      await loadUserProfiles();
      addLog(`器件库已删除: ${profile.model}`);
    } catch (error) {
      setLibraryError(`删除器件失败: ${error.message}`);
    }
  };
  const toggleUserProfileEnabled = async (profile) => {
    const nextEnabled = !profile.enabled;
    if (!window.confirm(`${nextEnabled ? "启用" : "禁用"} ${profile.model} 吗？`)) return;
    try {
      const data = await postJson("/api/user-profiles/toggle-enabled", {
        model: profile.model,
        enabled: nextEnabled,
      });
      setSelectedProfile(data.record || null);
      await loadUserProfiles();
      addLog(`器件库已${nextEnabled ? "启用" : "禁用"}: ${profile.model}`);
    } catch (error) {
      setLibraryError(`切换器件状态失败: ${error.message}`);
    }
  };
  useEffect(() => {
    if (rightPanel === "器件库") {
      loadUserProfiles();
    }
  }, [rightPanel]);

  const connect = async () => {
    if (connectionStatus === "checking") return;
    setConnectionStatus("checking");
    setDeviceSerial("");
    addLog(`开始探测${config.device} · ${config.runMode === "hardware" ? "硬件" : "开发仿真"}模式`);
    try {
      const data = await postJson("/api/connect", {
        mode: config.runMode,
        config: toBackendConfig(config),
      });
      setConnectionStatus("ready");
      setDeviceSerial(data.serial || "");
      addLog(`设备探测成功: ${data.serial || "unknown"}。当前没有执行输出，也没有采集数据。`);
    } catch (error) {
      setConnectionStatus("error");
      addLog(`设备探测失败: ${error.message}`);
    }
  };
  const disconnect = () => {
    setConnectionStatus("idle");
    setDeviceSerial("");
    addLog("已清除设备探测状态。");
  };
  const eStop = async () => {
    addLog("正在发送安全关断...");
    try {
      const data = await postJson("/api/emergency-off", { mode: config.runMode });
      setConnectionStatus("idle");
      setDeviceSerial("");
      addLog(data.message || "已发送安全关断。");
    } catch (error) {
      setConnectionStatus("error");
      addLog(`安全关断失败: ${error.message}`);
    }
  };
  const executeCurrentPlan = async () => {
    const plan = planWithCurrentEdits();
    if (!plan) {
      addLog("没有可执行计划，或测试点无效。");
      return;
    }
    if (config.runMode === "hardware") {
      const ok = window.confirm(`即将执行真实硬件输出。${HARDWARE_WARNING_DETAIL}继续吗？`);
      if (!ok) {
        addLog("已取消硬件执行。");
        return;
      }
    }
    setBusy(true);
    setCurrentPlan(plan);
    setMeasurements([]);
    setFocusMeasurement(null);
    addLog(`开始执行当前计划: ${plan.model} / ${plan.goal} / ${config.runMode}，共 ${plan.static_points.length} 个静态点。`);
    emitAgentEvent("BJTagent：执行开始，等待测量结果");
    try {
      const data = await postJson("/api/execute-plan", {
        mode: config.runMode,
        allow_hardware: config.runMode === "hardware",
        hardware_confirmation: config.runMode === "hardware" ? "确认硬件执行" : "",
        plan,
      });
      const execution = data.execution || {};
      if (execution.skipped) {
        addLog(`执行跳过: ${execution.reason || "未知原因"}`);
        return;
      }
      const nextMeasurements = applyMeasurements(execution.measurements || [], execution.latest_measurement || null);
      setDeviceSerial(execution.serial || deviceSerial);
      setConnectionStatus("ready");
      if (execution.aborted) {
        addLog(`执行已中止: ${execution.abort_reason || "未知原因"}`);
        addLog(`已保留 ${nextMeasurements.length} 个测量点`);
        emitAgentEvent("BJTagent：检测到执行中止，已保留现有测量点");
      } else {
        addLog(`执行完成: 采集 ${nextMeasurements.length} 个测量点。`);
        emitAgentEvent("BJTagent：执行完成，结果已返回界面");
      }
      if (execution.detected_bjt_type) addLog(`硬件识别结果: ${execution.detected_bjt_type}`);
    } catch (error) {
      setConnectionStatus("error");
      addLog(`执行失败: ${error.message}`);
    } finally {
      setBusy(false);
    }
  };
  const confirmHardware = (label) => {
    if (config.runMode !== "hardware") return true;
    return window.confirm(`即将执行真实硬件动作：${label}。${HARDWARE_WARNING_DETAIL}继续吗？`);
  };
  const runAction = async (requestedAction) => {
    const selectedMap = {
      beta: "static",
      vce_sat: "vce_sat",
      curves: "scan_curves",
      full: "full_suite",
    };
    const action = requestedAction === "selected" ? selectedMap[config.testGoal] || "static" : requestedAction;
    const label = {
      detect: "识别管型",
      selftest: "硬件自检",
      scope_check: "示波器检查",
      static: "静态点测试",
      vce_sat: "Vce(sat) 测试",
      scan_curves: "曲线扫描",
      full_suite: "完整测试",
    }[action] || action;
    if (!confirmHardware(label)) {
      addLog(`已取消${label}。`);
      return;
    }
    setBusy(true);
    if (["static", "vce_sat", "scan_curves", "full_suite"].includes(action)) {
      setMeasurements([]);
      setFocusMeasurement(null);
    }
    addLog(`开始${label} · ${config.runMode}`);
    try {
      const data = await postJson("/api/run-action", {
        action,
        mode: config.runMode,
        allow_hardware: config.runMode === "hardware",
        config: toBackendConfig(config),
        scan_mode: config.scanMode,
      });
      const result = data.result || {};
      if (result.serial) {
        setDeviceSerial(result.serial);
        setConnectionStatus("ready");
      }
      if (result.measurements) {
        const nextMeasurements = applyMeasurements(result.measurements, result.latest_measurement || null);
        addLog(`${label}完成: 采集 ${nextMeasurements.length} 个测量点。`);
      } else {
        addLog(`${label}完成。`);
      }
      if (result.detected_bjt_type) addLog(`识别结果: ${result.detected_bjt_type}`);
      if (result.vce_sat !== undefined) addLog(`Vce(sat): ${Number(result.vce_sat).toFixed(4)} V, Ic=${Number(result.ic_at_sat || 0).toExponential(3)} A`);
      if (result.beta_median !== undefined) addLog(`Beta 中位数: ${Number(result.beta_median).toFixed(1)}`);
      if (result.scope_mean) addLog(`CH1=${Number(result.scope_mean.ch1).toFixed(4)} V, CH2=${Number(result.scope_mean.ch2).toFixed(4)} V`);
      if (result.mean) addLog(`CH1=${Number(result.mean.ch1).toFixed(4)} V, CH2=${Number(result.mean.ch2).toFixed(4)} V`);
      if (result.output_dir) addLog(`报告输出目录: ${result.output_dir}`);
    } catch (error) {
      setConnectionStatus("error");
      addLog(`${label}失败: ${error.message}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="bjt-app" data-theme={theme}>
      <Styles />
      <div className="window">
        <TitleBar theme={theme} onToggleTheme={() => setTheme((t) => (t === "dark" ? "light" : "dark"))} />
        <div className="app">
          <Sidebar connectionStatus={connectionStatus} config={config} busy={busy} onConfigChange={updateConfig} onRunAction={runAction} onConnect={connect} onDisconnect={disconnect} onEStop={eStop} />
          <MainContent
            measurements={measurements}
            latestPoint={latestPoint}
            logs={logs}
            config={config}
            currentPlan={currentPlan}
            testPoints={testPoints}
            planLimits={planLimits}
            onConfigChange={updateConfig}
            onPointChange={changePoint}
            onAddPoint={addPoint}
            onRemovePoint={removePoint}
            onLimitChange={changeLimit}
            onApplyPlan={applyPlanEdits}
            onExecutePlan={executeCurrentPlan}
            busy={busy}
            onClearLog={() => setLogs([])}
          />
          {rightPanel === "BJTagent" ? (
            <AIPanel
              config={config}
              currentPlan={currentPlan}
              conversationState={conversationState}
              setConversationState={setConversationState}
              msgs={aiMessages}
              setMsgs={setAiMessages}
              tab={aiTab}
              setTab={setAiTab}
              provider={aiProvider}
              setProvider={setAiProvider}
              model={aiModel}
              setModel={setAiModel}
              apiKey={aiApiKey}
              setApiKey={setAiApiKey}
              text={aiText}
              setText={setAiText}
              agentStatus={agentStatus}
              agentEvent={agentEvent}
              testPoints={testPoints}
              planLimits={planLimits}
              measurements={measurements}
              logs={logs}
              onPlanReady={handlePlanReady}
              rightPanel={rightPanel}
              setRightPanel={setRightPanel}
              onOpenLibrary={openLibraryPanel}
            />
          ) : (
            <DeviceLibraryPanel
              rightPanel={rightPanel}
              setRightPanel={setRightPanel}
              loading={libraryLoading}
              error={libraryError}
              profiles={userProfiles}
              selectedProfile={selectedProfile}
              search={librarySearch}
              enabledOnly={libraryEnabledOnly}
              onSearchChange={(value) => {
                setLibrarySearch(value);
                setSelectedProfile(null);
                loadUserProfiles(value, libraryEnabledOnly);
              }}
              onEnabledOnlyChange={(value) => {
                setLibraryEnabledOnly(value);
                setSelectedProfile(null);
                loadUserProfiles(librarySearch, value);
              }}
              onRefresh={() => loadUserProfiles()}
              onSelectProfile={loadUserProfileDetail}
              onCreateProfile={createUserProfile}
              onEditProfile={editUserProfile}
              onDeleteProfile={deleteUserProfile}
              onToggleProfileEnabled={toggleUserProfileEnabled}
            />
          )}
        </div>
        <StatusBar connectionStatus={connectionStatus} deviceSerial={deviceSerial} config={config} />
      </div>
    </div>
  );
}

/* ============================== 设计令牌 + 样式 ============================== */
function Styles() {
  return (
    <style>{`
.bjt-app{
  --font-sans:-apple-system,BlinkMacSystemFont,"SF Pro Display","SF Pro Text","Helvetica Neue","PingFang SC","Microsoft YaHei",sans-serif;
  --font-mono:ui-monospace,"SF Mono","Menlo","Roboto Mono",monospace;
  --r-card:12px;--r-control:8px;--r-pill:999px;
  --s1:4px;--s2:8px;--s3:12px;--s4:16px;--s5:20px;--s6:24px;--s7:32px;--s8:40px;
  font-family:var(--font-sans);-webkit-font-smoothing:antialiased;color:var(--label);
  min-height:100%;display:flex;align-items:center;justify-content:center;padding:28px;box-sizing:border-box;
}
.bjt-app[data-theme="light"]{
  --blue:#007AFF;--red:#FF3B30;--green:#34C759;--orange:#FF9500;--gray:#8E8E93;
  --bg-window:#ECECEE;--bg-sidebar:rgba(246,246,248,.72);--bg-content:#F5F5F7;
  --bg-card:#FFF;--bg-control:#FFF;--bg-inset:#F2F2F7;
  --bg-fill:rgba(120,120,128,.12);--bg-fill-strong:rgba(120,120,128,.20);
  --label:#1D1D1F;--label-2:#6E6E73;--label-3:#9A9AA0;
  --separator:rgba(0,0,0,.08);--hairline:rgba(0,0,0,.10);--focus-ring:rgba(0,122,255,.35);
  --shadow-card:0 1px 2px rgba(0,0,0,.04),0 1px 8px rgba(0,0,0,.04);
  --shadow-window:0 24px 60px rgba(0,0,0,.22),0 2px 8px rgba(0,0,0,.12);
  --grid-line:rgba(0,0,0,.07);
  background:radial-gradient(1200px 800px at 15% -10%,rgba(0,122,255,.10),transparent 60%),radial-gradient(1000px 700px at 110% 120%,rgba(52,199,89,.08),transparent 55%),#d9d9de;
}
.bjt-app[data-theme="dark"]{
  --blue:#0A84FF;--red:#FF453A;--green:#30D158;--orange:#FF9F0A;--gray:#98989D;
  --bg-window:#1B1B1D;--bg-sidebar:rgba(40,40,43,.72);--bg-content:#1C1C1E;
  --bg-card:#2C2C2E;--bg-control:#3A3A3C;--bg-inset:#2C2C2E;
  --bg-fill:rgba(120,120,128,.24);--bg-fill-strong:rgba(120,120,128,.36);
  --label:#F5F5F7;--label-2:#AEAEB2;--label-3:#7C7C80;
  --separator:rgba(255,255,255,.10);--hairline:rgba(255,255,255,.14);--focus-ring:rgba(10,132,255,.5);
  --shadow-card:0 1px 3px rgba(0,0,0,.4);--shadow-window:0 28px 70px rgba(0,0,0,.6);
  --grid-line:rgba(255,255,255,.08);
  background:radial-gradient(1200px 800px at 15% -10%,rgba(10,132,255,.14),transparent 60%),radial-gradient(1000px 700px at 110% 120%,rgba(48,209,88,.10),transparent 55%),#0a0a0c;
}
.bjt-app *{box-sizing:border-box;margin:0;padding:0}

.window{width:min(1320px,100%);height:min(860px,calc(100vh - 56px));background:var(--bg-window);border-radius:14px;box-shadow:var(--shadow-window);overflow:hidden;display:flex;flex-direction:column;border:.5px solid var(--hairline);animation:bjtRise .5s cubic-bezier(.2,.8,.2,1)}
@keyframes bjtRise{from{opacity:0;transform:translateY(12px) scale(.99)}to{opacity:1;transform:none}}

.titlebar{height:44px;flex:0 0 44px;display:grid;grid-template-columns:1fr auto 1fr;align-items:center;padding:0 14px;background:var(--bg-sidebar);backdrop-filter:saturate(180%) blur(20px);-webkit-backdrop-filter:saturate(180%) blur(20px);border-bottom:.5px solid var(--separator);position:relative;z-index:5}
.traffic{display:flex;gap:8px}.traffic i{width:12px;height:12px;border-radius:50%;display:block}
.traffic .c{background:#FF5F57}.traffic .y{background:#FEBC2E}.traffic .g{background:#28C840}
.titlebar h1{font-size:13px;font-weight:600;color:var(--label-2);text-align:center}
.titlebar .right{display:flex;justify-content:flex-end}
.theme-btn{width:30px;height:30px;border-radius:8px;border:none;cursor:pointer;background:transparent;color:var(--label-2);display:grid;place-items:center;transition:background .15s}
.theme-btn:hover{background:var(--bg-fill)}

.app{flex:1;display:grid;grid-template-columns:268px minmax(0,1fr) 320px;min-height:0}
.sidebar{grid-area:sidebar;background:var(--bg-sidebar);backdrop-filter:saturate(180%) blur(20px);-webkit-backdrop-filter:saturate(180%) blur(20px);border-right:.5px solid var(--separator);padding:var(--s5) var(--s4) var(--s6);overflow-y:auto;min-width:0}
.content{grid-area:content;background:var(--bg-content);overflow-y:auto;padding:var(--s7) var(--s7) var(--s8);min-width:0}
.inspector{grid-area:inspector;background:var(--bg-sidebar);backdrop-filter:saturate(180%) blur(20px);-webkit-backdrop-filter:saturate(180%) blur(20px);border-left:.5px solid var(--separator);display:flex;flex-direction:column;min-height:0;min-width:0}
.bjt-app ::-webkit-scrollbar{width:9px;height:9px}
.bjt-app ::-webkit-scrollbar-thumb{background:var(--bg-fill-strong);border-radius:99px;border:2px solid transparent;background-clip:padding-box}

.group{margin-bottom:var(--s6)}
.group-title{font-size:12px;font-weight:600;color:var(--label-3);letter-spacing:.04em;text-transform:uppercase;padding:0 var(--s1) var(--s2)}
.list{background:var(--bg-card);border-radius:var(--r-card);box-shadow:var(--shadow-card);overflow:hidden}
.row{display:flex;align-items:center;gap:var(--s3);padding:10px var(--s4);min-height:38px;position:relative}
.row+.row::before{content:"";position:absolute;left:var(--s4);right:0;top:0;height:.5px;background:var(--separator)}
.row .lbl{font-size:13px;color:var(--label)}
.row .val{margin-left:auto;font-size:13px;color:var(--label-2);display:flex;align-items:center;gap:6px}
.row .val .unit{color:var(--label-3);font-size:12px}
.row.input .val input{font-family:var(--font-mono);font-size:13px;color:var(--label);border:none;background:transparent;text-align:right;width:110px;outline:none}
.row.select .val{color:var(--blue);position:relative}
.row.select .val select{appearance:none;-webkit-appearance:none;border:none;background:transparent;color:var(--blue);font-family:var(--font-sans);font-size:13px;font-weight:510;line-height:20px;outline:none;padding:2px 18px 2px 2px;text-align:right;text-align-last:right;cursor:pointer;max-width:138px}
.row.select .val select:focus-visible{border-radius:6px;box-shadow:0 0 0 3px var(--focus-ring)}
.row.select .val .chev{position:absolute;right:0;pointer-events:none}
.chev{color:var(--label-3)}
.opt{cursor:pointer;transition:background .12s}
.opt:hover{background:var(--bg-fill)}
.opt .check{margin-left:auto;color:var(--blue);opacity:0;transition:opacity .12s}
.opt.sel .check{opacity:1}.opt.sel .lbl{font-weight:590}
.opt .ico{width:22px;height:22px;border-radius:6px;display:grid;place-items:center;color:#fff;flex:0 0 22px;font-size:13px}

.seg{display:flex;background:var(--bg-fill);border-radius:var(--r-control);padding:2px;gap:2px}
.seg button{flex:1;border:none;background:transparent;cursor:pointer;padding:5px 10px;font-family:var(--font-sans);font-size:13px;color:var(--label);border-radius:6px;font-weight:510;transition:all .18s;white-space:nowrap}
.seg button.on{background:var(--bg-card);box-shadow:0 1px 3px rgba(0,0,0,.12);font-weight:590}
.bjt-app[data-theme="dark"] .seg button.on{background:#636366}

.status{display:inline-flex;align-items:center;gap:7px;font-size:13px;font-weight:590;color:var(--label)}
.dot{width:9px;height:9px;border-radius:50%;background:var(--gray);box-shadow:0 0 0 3px var(--bg-fill)}
.dot.on{background:var(--green);box-shadow:0 0 0 3px rgba(52,199,89,.22)}

.btns{display:flex;gap:var(--s2);margin-top:var(--s3)}
.btn{flex:1;border:none;cursor:pointer;padding:8px 14px;border-radius:var(--r-control);font-family:var(--font-sans);font-size:13px;font-weight:590;transition:all .15s}
.btn:disabled{opacity:.55;cursor:not-allowed}
.btn:active{transform:scale(.975)}
.btn.primary{background:var(--blue);color:#fff}.btn.primary:hover{filter:brightness(1.07)}
.btn.plain{background:var(--bg-fill);color:var(--label)}.btn.plain:hover{background:var(--bg-fill-strong)}
.btn.danger{background:var(--red);color:#fff;width:100%;margin-top:var(--s4)}.btn.danger:hover{filter:brightness(1.06)}
.op-actions{display:flex;gap:var(--s2);margin-top:var(--s3)}

.switch{position:relative;width:51px;height:31px;flex:0 0 51px;cursor:pointer;display:inline-block}
.switch input{display:none}
.switch .track{position:absolute;inset:0;background:var(--bg-fill-strong);border-radius:99px;transition:background .25s}
.switch .knob{position:absolute;top:2px;left:2px;width:27px;height:27px;background:#fff;border-radius:50%;box-shadow:0 2px 5px rgba(0,0,0,.25);transition:transform .25s cubic-bezier(.3,1.4,.6,1)}
.switch input:checked~.track{background:var(--green)}
.switch input:checked~.knob{transform:translateX(20px)}

.page-head{display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:var(--s6)}
.page-head h2{font-size:28px;font-weight:700;letter-spacing:-.02em;line-height:1.1}
.page-head .sub{font-size:15px;color:var(--label-2);margin-top:3px}
.mode-toggle{display:flex;align-items:center;gap:10px;font-size:13px;color:var(--label-2);background:var(--bg-card);padding:7px 7px 7px 14px;border-radius:var(--r-pill);box-shadow:var(--shadow-card)}

.card{background:var(--bg-card);border-radius:var(--r-card);box-shadow:var(--shadow-card);padding:var(--s5)}
.card-h{display:flex;align-items:center;justify-content:space-between;margin-bottom:var(--s4)}
.card-h h3{font-size:15px;font-weight:640;letter-spacing:-.01em}
.card-h .meta{font-size:12px;color:var(--label-3);margin-left:auto}
.section{margin-bottom:var(--s5)}

.chart-wrap{position:relative}
.chart-empty{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px;color:var(--label-3);transition:opacity .3s}
.chart-empty .pulse{width:46px;height:46px;border-radius:14px;background:var(--bg-fill);display:grid;place-items:center;color:var(--gray)}
.chart-empty span{font-size:14px}.chart-empty .hint{font-size:12px;color:var(--label-3)}
.chart-card.connected .chart-empty{opacity:0;pointer-events:none}
svg .axis{stroke:var(--label-3);stroke-width:1}
svg .grid{stroke:var(--grid-line);stroke-width:1}
svg .tick{fill:var(--label-3);font-size:11px;font-family:var(--font-mono)}
svg .axt{fill:var(--label-2);font-size:12px;font-family:var(--font-sans)}
svg .curve{fill:none;stroke:var(--blue);stroke-width:2;stroke-linecap:round;opacity:0;transition:opacity .5s}
.chart-card.connected svg .curve{opacity:1}
svg .clabel{fill:var(--label-3);font-size:10px;font-family:var(--font-mono);opacity:0;transition:opacity .5s;paint-order:stroke;stroke:var(--bg-card);stroke-width:3px;stroke-linejoin:round}
.chart-card.connected svg .clabel{opacity:1}
svg .sample-dot{fill:var(--blue);stroke:var(--bg-card);stroke-width:2}

.metrics{display:grid;grid-template-columns:repeat(3,1fr);gap:var(--s3)}
.metric{background:var(--bg-card);border-radius:var(--r-card);padding:var(--s4);box-shadow:var(--shadow-card)}
.metric .k{font-size:12px;color:var(--label-2);display:flex;align-items:center;gap:6px}
.metric .k b{font-family:var(--font-mono);font-weight:600;color:var(--label-3)}
.metric .v{font-family:var(--font-mono);font-size:26px;font-weight:600;letter-spacing:-.01em;margin-top:6px;color:var(--label)}
.metric .v small{font-size:13px;color:var(--label-3);font-weight:500;margin-left:3px}
.metric .v.idle{color:var(--label-3)}
.metric .region{font-size:13px;font-weight:600;display:inline-flex;align-items:center;gap:6px;padding:3px 10px;border-radius:99px;background:rgba(52,199,89,.14);color:var(--green)}

.two-col{display:grid;grid-template-columns:1.3fr 1fr;gap:var(--s5)}
.tp-actions{display:flex;gap:var(--s2);margin-left:auto}
.chip{border:none;cursor:pointer;padding:6px 12px;border-radius:7px;background:var(--bg-fill);color:var(--label);font-family:var(--font-sans);font-size:12px;font-weight:540;transition:background .12s}
.chip:hover{background:var(--bg-fill-strong)}
.chip.go{background:rgba(0,122,255,.12);color:var(--blue)}
.chip.run{background:var(--blue);color:#fff}
.chip:disabled{opacity:.48;cursor:not-allowed}
.tp-inputs{display:flex;gap:var(--s4);margin:var(--s4) 0}
.field{flex:1}.field label{display:block;font-size:12px;color:var(--label-2);margin-bottom:5px}
.field .inp{width:100%;background:var(--bg-inset);border:.5px solid var(--separator);border-radius:var(--r-control);padding:7px 11px;font-family:var(--font-mono);font-size:13px;color:var(--label);outline:none;transition:box-shadow .15s,border-color .15s}
.field .inp:focus{border-color:var(--blue);box-shadow:0 0 0 3px var(--focus-ring)}
.tp-table{border-radius:var(--r-control);overflow:hidden;border:.5px solid var(--separator)}
.tp-table .th{display:grid;grid-template-columns:1fr 1fr 88px;background:var(--bg-inset)}
.tp-table .th span{padding:8px 12px;font-size:12px;font-weight:600;color:var(--label-2)}
.tp-table .th span:first-child{border-right:.5px solid var(--separator)}
.tp-row{display:grid;grid-template-columns:1fr 1fr 88px;border-top:.5px solid var(--separator)}
.tp-row input{min-width:0;border:none;border-right:.5px solid var(--separator);background:transparent;color:var(--label);font-family:var(--font-mono);font-size:12px;padding:8px 12px;outline:none}
.tp-row input:focus{background:var(--bg-inset)}
.tp-row span{padding:8px 12px;color:var(--label-3);font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.empty-mini{color:var(--label-3);font-size:13px;padding:14px 0;text-align:center}
.log-box{background:var(--bg-inset);border-radius:var(--r-control);padding:var(--s3);min-height:120px;max-height:150px;overflow-y:auto;font-family:var(--font-mono);font-size:12px;color:var(--label-2);line-height:1.7}
.log-box .ln{display:flex;gap:8px}.log-box .ln .t{color:var(--label-3)}
.log-empty{color:var(--label-3);display:grid;place-items:center;height:96px;font-family:var(--font-sans)}
.log-foot{margin-top:var(--s3)}

.insp-head{display:flex;align-items:center;justify-content:space-between;padding:var(--s5) var(--s5) var(--s3)}
.insp-head h3{font-size:15px;font-weight:700;letter-spacing:-.01em}
.insp-head .clear{border:none;background:transparent;color:var(--blue);font-size:13px;cursor:pointer;font-family:var(--font-sans)}
.agent-card{margin:0 var(--s5) var(--s4);padding:12px;border-radius:var(--r-card);background:var(--bg-card);box-shadow:var(--shadow-card);display:flex;flex-direction:column;gap:8px}
.agent-card-head{display:flex;align-items:center;justify-content:space-between;gap:10px}
.agent-card-head strong{font-size:14px;font-weight:700}
.agent-badge{display:inline-flex;align-items:center;justify-content:center;padding:4px 10px;border-radius:999px;background:rgba(0,122,255,.12);color:var(--blue);font-size:12px;font-weight:600}
.agent-line{font-size:12px;line-height:1.5;color:var(--label-2)}
.insp-tabs{padding:0 var(--s5) var(--s4)}
.chat{flex:1;overflow-y:auto;padding:var(--s2) var(--s5);display:flex;flex-direction:column;gap:var(--s3)}
.intro{color:var(--label-2);font-size:13px;line-height:1.6}
.intro b{color:var(--label);font-weight:640;display:block;margin-bottom:6px;font-size:14px}
.bubble{max-width:92%;padding:10px 13px;border-radius:16px;font-size:13px;line-height:1.55}
.bubble.ai{background:var(--bg-fill);color:var(--label);align-self:flex-start;border-bottom-left-radius:5px}
.bubble.me{background:var(--blue);color:#fff;align-self:flex-end;border-bottom-right-radius:5px}
.bubble.system{align-self:center;background:var(--bg-fill);color:var(--label-2);border:1px dashed var(--separator);max-width:96%}
.composer{border-top:.5px solid var(--separator);padding:var(--s4) var(--s5) var(--s5);display:flex;flex-direction:column;gap:var(--s2);background:var(--bg-sidebar)}
.service{border:none;border-radius:var(--r-control);padding:8px 11px;font-family:var(--font-sans);font-size:12px;font-weight:640;cursor:pointer;text-align:left}
.service.on{background:rgba(52,199,89,.14);color:var(--green)}
.service.off{background:rgba(255,149,0,.16);color:var(--orange)}
.composer .mini{width:100%;background:var(--bg-control);border:.5px solid var(--separator);border-radius:var(--r-control);padding:8px 11px;font-family:var(--font-mono);font-size:12px;color:var(--label);outline:none}
.composer textarea{width:100%;background:var(--bg-control);border:.5px solid var(--separator);border-radius:var(--r-control);padding:10px 11px;font-family:var(--font-sans);font-size:13px;color:var(--label);resize:none;height:64px;outline:none;transition:box-shadow .15s,border-color .15s}
.composer textarea:focus,.composer .mini:focus{border-color:var(--blue);box-shadow:0 0 0 3px var(--focus-ring)}
.send{border:none;background:var(--blue);color:#fff;padding:10px;border-radius:var(--r-control);font-family:var(--font-sans);font-size:14px;font-weight:640;cursor:pointer;transition:filter .15s,transform .1s}
.send:hover{filter:brightness(1.07)}.send:active{transform:scale(.98)}

.statusbar{flex:0 0 28px;display:flex;align-items:center;padding:0 var(--s4);border-top:.5px solid var(--separator);background:var(--bg-sidebar);font-size:12px;color:var(--label-2);gap:7px}

.stagger>*{opacity:0;animation:bjtFade .5s forwards}
.stagger>*:nth-child(1){animation-delay:.05s}.stagger>*:nth-child(2){animation-delay:.1s}.stagger>*:nth-child(3){animation-delay:.15s}
@keyframes bjtFade{to{opacity:1}}

@media (max-width:1080px){.app{grid-template-columns:220px minmax(0,1fr);grid-template-areas:"sidebar content" "sidebar inspector"}.inspector{border-left:none;border-top:.5px solid var(--separator);max-height:360px}.metrics{grid-template-columns:repeat(2,1fr)}.content{padding:var(--s6) var(--s5) var(--s7)}}
@media (max-width:820px){.window{height:auto;min-height:calc(100vh - 56px)}.app{grid-template-columns:1fr;grid-template-areas:"sidebar" "content" "inspector"}.sidebar{border-right:none;border-bottom:.5px solid var(--separator)}.inspector{max-height:none}}
`}</style>
  );
}
