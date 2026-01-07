import gi, time
gi.require_version("Gst", "1.0")
from gi.repository import Gst, GLib

Gst.init(None)

# 비밀번호에 '@' 포함 → %40
RTSP_URL = "rtsp://admin:kakaorobot%40@192.168.10.101:554/Streaming/Channels/101"

PIPE = (
    f'rtspsrc location="{RTSP_URL}" protocols=tcp latency=30 drop-on-latency=true ! '
    'rtph264depay ! h264parse ! avdec_h264 ! videoconvert ! '
    'tee name=t '
    # (1) 화면 표시 브랜치
    't. ! queue max-size-buffers=1 leaky=downstream ! autovideosink sync=false '
    # (2) 지연 측정 브랜치 (appsink로 sample/segment 확보)
    't. ! queue max-size-buffers=1 leaky=downstream ! '
    'appsink name=msink emit-signals=true sync=false max-buffers=1 drop=true'
)

pipeline = Gst.parse_launch(PIPE)
appsink = pipeline.get_by_name("msink")

_last_print = 0.0

def on_new_sample(sink):
    global _last_print

    sample = sink.emit("pull-sample")
    if sample is None:
        return Gst.FlowReturn.OK

    buf = sample.get_buffer()
    if buf is None or buf.pts == Gst.CLOCK_TIME_NONE:
        return Gst.FlowReturn.OK

    # 핵심: sample의 segment로 PTS를 running-time으로 변환
    seg = sample.get_segment()
    pts_rt = seg.to_running_time(Gst.Format.TIME, buf.pts)
    if pts_rt == Gst.CLOCK_TIME_NONE:
        return Gst.FlowReturn.OK

    # 현재 pipeline running-time
    clock = pipeline.get_clock()
    if clock is None:
        return Gst.FlowReturn.OK
    now_rt = clock.get_time() - pipeline.get_base_time()

    latency_ms = (now_rt - pts_rt) / 1e6

    t = time.time()
    if t - _last_print >= 0.5:  # 0.5초마다 1번 출력
        print(f"Latency: {latency_ms:.1f} ms")
        _last_print = t

    return Gst.FlowReturn.OK

appsink.connect("new-sample", on_new_sample)

# bus 처리
loop = GLib.MainLoop()
bus = pipeline.get_bus()
bus.add_signal_watch()

def on_message(bus, message):
    if message.type == Gst.MessageType.ERROR:
        err, dbg = message.parse_error()
        print("[Gst ERROR]", err)
        if dbg:
            print("[Gst DEBUG]", dbg)
        loop.quit()
    elif message.type == Gst.MessageType.EOS:
        loop.quit()

bus.connect("message", on_message)

pipeline.set_state(Gst.State.PLAYING)
try:
    loop.run()
except KeyboardInterrupt:
    pass
finally:
    pipeline.set_state(Gst.State.NULL)
