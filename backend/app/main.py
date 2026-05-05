from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import json
import uvicorn
from db.database import save_test_record
from hardware.hardware_tester import BJTTester

app = FastAPI(title="BJT Automated Test System API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

tester = BJTTester()

@app.on_event("startup")
async def startup_event():
    tester.connect()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            payload = json.loads(data)
            
            if payload.get("command") == "start":
                params = payload.get("params", {})
                device_type = tester.detect_device()
                
                # 通知前端已识别器件
                await websocket.send_json({"type": "status", "device": device_type, "stage": "测试中"})
                
                raw_data = []
                beta_list = []
                vce_sat_list = []
                
                async def on_data_point(point):
                    if "error" in point:
                        await websocket.send_json({"type": "error", "message": point["error"]})
                        return
                    
                    raw_data.append(point)
                    if point["Beta"] > 0:
                        beta_list.append(point["Beta"])
                    if point["Vce"] < 0.5 and point["VCE_SAT"] > 0:
                        vce_sat_list.append(point["VCE_SAT"])
                        
                    await websocket.send_json({"type": "data", "point": point})
                
                # 执行自动扫描
                await tester.run_sweep(params, on_data_point)
                
                # 计算总体参数与线性度并存库
                if len(beta_list) > 0:
                    b_avg = sum(beta_list) / len(beta_list)
                    b_max = max(beta_list)
                    b_min = min(beta_list)
                    b_linearity = ((b_max - b_min) / b_avg) * 100 if b_avg > 0 else 0
                    v_sat = sum(vce_sat_list)/len(vce_sat_list) if vce_sat_list else 0
                    
                    save_test_record(
                        device_type=device_type,
                        beta_avg=b_avg,
                        beta_max=b_max,
                        beta_min=b_min,
                        beta_linearity=b_linearity,
                        vce_sat=v_sat,
                        raw_data=raw_data
                    )
                
                await websocket.send_json({"type": "status", "device": device_type, "stage": "空闲"})
                await websocket.send_json({"type": "done"})
                
            elif payload.get("command") == "stop":
                tester.stop()
                await websocket.send_json({"type": "status", "stage": "空闲"})
                
    except WebSocketDisconnect:
        tester.stop()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
