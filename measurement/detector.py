from __future__ import annotations


def detect_bjt_type(driver, R_B: float, R_C: float) -> str:
    driver.set_v_pos(3.0)
    driver.set_w1_dc(2.0)
    try:
        vb, vc = driver.read_scope_mean(samples=512)
        
        if abs(vb) < 0.1 and abs(vc) < 0.1:
            raise RuntimeError("未检测到有效电压，请检查测试夹具是否正确连接！")
            
        if abs(vb - 2.0) < 0.1 and abs(vc - 3.0) < 0.1:
            raise RuntimeError("未检测到器件接入 (开路)，请插入晶体管！")

        ib = max((2.0 - float(vb)) / float(R_B), 0.0)
        ic = max((3.0 - float(vc)) / float(R_C), 0.0)
        beta = ic / ib if ib > 1e-12 else 0.0
        
        if beta >= 10.0 and 0.4 < vb < 0.9:
            return "NPN"
        if abs(float(vb) - 2.0) < 0.3 and abs(float(vc) - 3.0) < 0.2:
            return "SUSPECTED_PNP"
        return "UNKNOWN"
    finally:
        disable_all = getattr(driver, "disable_all", None)
        if callable(disable_all):
            disable_all()
        else:
            driver.emergency_off()
