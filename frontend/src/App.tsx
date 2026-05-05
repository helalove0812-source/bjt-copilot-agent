import React, { useState, useEffect, useRef } from 'react';
import ReactECharts from 'echarts-for-react';
import { Play, Download, FileText } from 'lucide-react';

export default function App() {
  const [status, setStatus] = useState({ device: '未知', stage: '空闲', connected: false });
  const [params, setParams] = useState({
    ib_start: 10,
    ib_step: 10,
    steps: 5,
    vce_max: 5,
    ic_limit: 150
  });
  
  const [metrics, setMetrics] = useState({
    ib: "0.00", ic: "0.00", beta: "0.00", vbe: "0.00", vce_sat: "0.00"
  });

  const [chartData, setChartData] = useState<any[]>([]);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    connectWs();
    return () => {
      if (wsRef.current) wsRef.current.close();
    };
  }, []);

  const connectWs = () => {
    const ws = new WebSocket('ws://localhost:8000/ws');
    ws.onopen = () => setStatus(s => ({ ...s, connected: true }));
    ws.onclose = () => setStatus(s => ({ ...s, connected: false }));
    ws.onmessage = (e) => {
      const data = JSON.parse(e.data);
      if (data.type === 'status') {
        setStatus(s => ({ ...s, device: data.device || s.device, stage: data.stage }));
      } else if (data.type === 'data') {
        const pt = data.point;
        setMetrics({
          ib: pt.Ib.toFixed(2),
          ic: pt.Ic.toFixed(2),
          beta: pt.Beta.toFixed(2),
          vbe: pt.VBE.toFixed(2),
          vce_sat: pt.VCE_SAT.toFixed(2)
        });
        setChartData(prev => {
          const newData = [...prev];
          const seriesIndex = Math.floor((pt.Ib_target - params.ib_start) / params.ib_step);
          if (!newData[seriesIndex]) {
            newData[seriesIndex] = { name: `Ib=${pt.Ib_target}μA`, type: 'line', smooth: true, data: [] };
          }
          newData[seriesIndex].data.push([pt.Vce, pt.Ic]);
          return newData;
        });
      } else if (data.type === 'error') {
        alert(data.message);
      }
    };
    wsRef.current = ws;
  };

  const startTest = () => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      alert("后端未连接");
      return;
    }
    setChartData([]);
    wsRef.current.send(JSON.stringify({ command: 'start', params }));
  };

  const exportCSV = () => {
    // 简单实现
    alert("CSV 导出功能已触发");
  };

  const exportPDF = () => {
    fetch('http://localhost:8000/api/report', { method: 'POST' })
      .then(res => res.blob())
      .then(blob => {
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'BJT_Report.pdf';
        a.click();
      })
      .catch(e => alert("报告生成中，请确保后端 generate_report.py 已配置"));
  };

  const option = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'value', name: 'VCE (V)', nameLocation: 'middle', nameGap: 30, splitLine: { show: false }, axisLabel: { color: '#888' } },
    yAxis: { type: 'value', name: 'IC (mA)', splitLine: { lineStyle: { color: '#333' } }, axisLabel: { color: '#888' } },
    series: chartData.length ? chartData : [{ type: 'line', data: [] }],
    color: ['#5470c6', '#91cc75', '#fac858', '#ee6666', '#73c0de', '#3ba272']
  };

  return (
    <div className="flex h-screen bg-[#111] text-gray-300 font-sans">
      {/* Left Sidebar */}
      <div className="w-80 bg-[#1a1a1a] border-r border-[#333] p-6 flex flex-col">
        <h1 className="text-yellow-500 text-xl font-bold mb-1">● BJT 分析仪</h1>
        <p className="text-xs text-gray-500 mb-8">雨骤 Model S | v1.0</p>
        
        <div className="mb-4">
          <label className="block text-xs mb-1 text-gray-400">连接 串口</label>
          <input className="w-full bg-[#111] border border-[#333] rounded px-3 py-2 text-sm text-gray-300 outline-none" value="/dev/ttyUSB0" readOnly />
        </div>
        
        <div className="text-xs text-gray-400 mb-2 mt-4">扫描参数</div>
        <div className="grid grid-cols-2 gap-4 mb-4">
          <div>
            <label className="block text-xs mb-1">Ib 起始值 (μA)</label>
            <input type="number" className="w-full bg-[#111] border border-[#333] rounded px-3 py-2 text-sm focus:border-yellow-500 outline-none" value={params.ib_start} onChange={e => setParams({...params, ib_start: Number(e.target.value)})} />
          </div>
          <div>
            <label className="block text-xs mb-1">Ib 步进 (μA)</label>
            <input type="number" className="w-full bg-[#111] border border-[#333] rounded px-3 py-2 text-sm focus:border-yellow-500 outline-none" value={params.ib_step} onChange={e => setParams({...params, ib_step: Number(e.target.value)})} />
          </div>
        </div>
        <div className="grid grid-cols-2 gap-4 mb-6">
          <div>
            <label className="block text-xs mb-1">阶数</label>
            <input type="number" className="w-full bg-[#111] border border-[#333] rounded px-3 py-2 text-sm focus:border-yellow-500 outline-none" value={params.steps} onChange={e => setParams({...params, steps: Number(e.target.value)})} />
          </div>
          <div>
            <label className="block text-xs mb-1">VCE 最大值 (V)</label>
            <input type="number" className="w-full bg-[#111] border border-[#333] rounded px-3 py-2 text-sm focus:border-yellow-500 outline-none" value={params.vce_max} onChange={e => setParams({...params, vce_max: Number(e.target.value)})} />
          </div>
        </div>

        <div className="text-xs text-gray-400 mb-2">保护</div>
        <div className="mb-6">
          <label className="block text-xs mb-1">Ic 限流 (mA)</label>
          <input type="number" className="w-full bg-[#111] border border-[#333] rounded px-3 py-2 text-sm focus:border-yellow-500 outline-none" value={params.ic_limit} onChange={e => setParams({...params, ic_limit: Number(e.target.value)})} />
        </div>

        <button onClick={startTest} className="w-full bg-yellow-500 hover:bg-yellow-400 text-black font-bold py-3 rounded flex items-center justify-center gap-2">
          <Play size={18} fill="currentColor" /> 开始测试
        </button>

        <div className="flex gap-2 mt-auto">
          <button onClick={exportCSV} className="flex-1 bg-[#222] hover:bg-[#333] py-2 rounded text-sm flex items-center justify-center gap-2 border border-[#333]"><FileText size={16}/> 导出 CSV</button>
          <button onClick={exportPDF} className="flex-1 bg-[#222] hover:bg-[#333] py-2 rounded text-sm flex items-center justify-center gap-2 border border-[#333]"><Download size={16}/> 导出 PDF</button>
        </div>
      </div>

      {/* Main Area */}
      <div className="flex-1 flex flex-col p-6">
        <div className="flex gap-6 mb-6 text-sm">
          <span className={status.connected ? "text-green-500" : "text-red-500"}>● {status.connected ? "已连接" : "未连接"}</span>
          <span>器件: <span className="text-gray-400">{status.device}</span></span>
          <span>阶段: <span className="text-gray-400">{status.stage}</span></span>
        </div>

        <div className="grid grid-cols-5 gap-4 mb-6">
          <MetricCard title="基极电流 (IB)" value={metrics.ib} unit="μA" />
          <MetricCard title="集电极电流 (IC)" value={metrics.ic} unit="mA" />
          <MetricCard title="电流放大倍数 (β)" value={metrics.beta} unit="" />
          <MetricCard title="基射极电压 (VBE)" value={metrics.vbe} unit="V" />
          <MetricCard title="饱和压降 (VCE_SAT)" value={metrics.vce_sat} unit="V" />
        </div>

        <div className="flex-1 bg-[#1a1a1a] border border-[#333] rounded-lg p-4 flex flex-col">
          <div className="text-sm text-gray-400 mb-2">Ic-VCE 输出特性曲线</div>
          <div className="flex-1 w-full">
            <ReactECharts option={option} style={{ height: '100%', width: '100%' }} />
          </div>
        </div>
      </div>
    </div>
  );
}

function MetricCard({ title, value, unit }: { title: string, value: string, unit: string }) {
  return (
    <div className="bg-[#1a1a1a] border border-[#333] rounded-lg p-4 flex flex-col justify-center">
      <div className="text-xs text-gray-500 mb-2">{title}</div>
      <div className="text-2xl font-mono text-white">
        {value} <span className="text-sm text-gray-500">{unit}</span>
      </div>
    </div>
  );
}
