import argparse
import csv
import os
import shutil
import subprocess
import sys
import time
from urllib.parse import urlparse

import cv2
import numpy as np


def parse_args():
    parser = argparse.ArgumentParser(
        description="Track red laser spot in video and export trajectory CSV."
    )
    parser.add_argument(
        "--youtube-url",
        default="",
        help="YouTube watch URL. If provided, this overrides --input.",
    )
    parser.add_argument(
        "--input",
        default=os.path.join("video", "video.mp4"),
        help="Input video path.",
    )
    parser.add_argument(
        "--yt-format",
        default="bv*[ext=mp4]/best[ext=mp4]/best",
        help="yt-dlp format selector used for YouTube streaming.",
    )
    parser.add_argument(
        "--yt-remote-components",
        default="ejs:github",
        help="yt-dlp remote component sources (empty string to disable).",
    )
    parser.add_argument(
        "--yt-js-runtime",
        default="",
        help="Explicit JavaScript runtime for yt-dlp, e.g. node:C:\\path\\to\\node.exe",
    )
    parser.add_argument(
        "--output-video",
        default="laser_output_enhanced.mp4",
        help="Output annotated video path.",
    )
    parser.add_argument(
        "--output-csv",
        default="laser_data_enhanced.csv",
        help="Output CSV path.",
    )
    parser.add_argument(
        "--write-video",
        action="store_true",
        help="Write annotated output video.",
    )
    parser.add_argument(
        "--start-frame",
        type=int,
        default=0,
        help="Start processing from this frame.",
    )
    parser.add_argument(
        "--max-frames",
        type=int,
        default=0,
        help="Maximum number of frames to process (0 means all).",
    )
    parser.add_argument(
        "--every-n-frames",
        type=int,
        default=1,
        help="Process every Nth frame.",
    )
    parser.add_argument("--min-brightness", type=int, default=180)
    parser.add_argument("--min-area", type=float, default=15.0)
    parser.add_argument("--max-area", type=float, default=300.0)
    parser.add_argument("--min-circularity", type=float, default=0.5)
    parser.add_argument("--lost-threshold", type=int, default=30)
    parser.add_argument("--base-search-radius", type=int, default=50)
    parser.add_argument("--max-search-radius", type=int, default=200)
    parser.add_argument(
        "--scale",
        type=float,
        default=1.0,
        help="Detection scale factor, e.g. 0.5 for faster processing.",
    )
    parser.add_argument(
        "--quiet-progress",
        action="store_true",
        help="Disable terminal progress updates (safer for long non-interactive runs).",
    )
    return parser.parse_args()


def draw_progress_bar(current, total, start_time, status):
    if total <= 0:
        return
    percent = current / total
    bar_len = 24
    done = int(percent * bar_len)
    bar = "#" * done + "-" * (bar_len - done)
    elapsed = time.time() - start_time
    eta = (elapsed / percent) - elapsed if percent > 0 else 0.0
    try:
        sys.stdout.write(
            f"\r|{bar}| {percent:6.2%} | mode={status:<9} | elapsed={elapsed:7.1f}s | eta={eta:7.1f}s"
        )
        sys.stdout.flush()
    except OSError:
        # Some non-interactive consoles can raise OSError on frequent flush/write.
        pass


def build_red_mask(frame_bgr, clahe, min_brightness):
    # Enhance local contrast on lightness channel for better red spot detection.
    lab = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2LAB)
    l_chan, a_chan, b_chan = cv2.split(lab)
    l_enhanced = clahe.apply(l_chan)
    enhanced = cv2.cvtColor(cv2.merge((l_enhanced, a_chan, b_chan)), cv2.COLOR_LAB2BGR)

    blurred = cv2.GaussianBlur(enhanced, (5, 5), 0)
    hsv = cv2.cvtColor(blurred, cv2.COLOR_BGR2HSV)

    lower_red1 = np.array([0, 10, min_brightness], dtype=np.uint8)
    upper_red1 = np.array([10, 255, 255], dtype=np.uint8)
    lower_red2 = np.array([160, 10, min_brightness], dtype=np.uint8)
    upper_red2 = np.array([180, 255, 255], dtype=np.uint8)

    mask1 = cv2.inRange(hsv, lower_red1, upper_red1)
    mask2 = cv2.inRange(hsv, lower_red2, upper_red2)
    return cv2.bitwise_or(mask1, mask2)


def contour_candidates(mask, min_area, max_area):
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates = []
    for contour in contours:
        area = cv2.contourArea(contour)
        if not (min_area < area < max_area):
            continue
        perimeter = cv2.arcLength(contour, True)
        if perimeter <= 0:
            continue
        circularity = 4.0 * np.pi * (area / (perimeter * perimeter))
        moments = cv2.moments(contour)
        if moments["m00"] == 0:
            continue
        cx = int(moments["m10"] / moments["m00"])
        cy = int(moments["m01"] / moments["m00"])
        candidates.append({"pos": (cx, cy), "area": area, "circ": circularity})
    return candidates


def is_youtube_url(value):
    if not value:
        return False
    parsed = urlparse(value)
    host = parsed.netloc.lower()
    return ("youtube.com" in host) or ("youtu.be" in host)


def detect_node_runtime(runtime_arg):
    if runtime_arg:
        return runtime_arg

    node_in_path = shutil.which("node")
    if node_in_path:
        return f"node:{node_in_path}"

    common_paths = [
        r"C:\Program Files\nodejs\node.exe",
        r"C:\Program Files (x86)\nodejs\node.exe",
    ]
    for path in common_paths:
        if os.path.exists(path):
            return f"node:{path}"
    return ""


def find_yt_dlp_cli():
    cli = shutil.which("yt-dlp")
    if cli:
        return cli

    local_cli = os.path.join(os.path.dirname(__file__), ".venv", "Scripts", "yt-dlp.exe")
    if os.path.exists(local_cli):
        return local_cli
    return ""


def resolve_youtube_stream_url(youtube_url, yt_format, yt_remote_components, yt_js_runtime):
    errors = []
    js_runtime = detect_node_runtime(yt_js_runtime)

    # Try yt-dlp CLI first.
    yt_dlp_cli = find_yt_dlp_cli()
    if yt_dlp_cli:
        command = [yt_dlp_cli]
        if js_runtime:
            command += ["--js-runtimes", js_runtime]
        if yt_remote_components:
            command += ["--remote-components", yt_remote_components]
        command += ["-g", "-f", yt_format, youtube_url]

        try:
            proc = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=True,
            )
            for line in proc.stdout.splitlines():
                line = line.strip()
                if line.startswith("http://") or line.startswith("https://"):
                    return line, "yt-dlp-cli"
            errors.append("yt-dlp CLI returned no stream URL.")
        except subprocess.CalledProcessError as exc:
            message = (exc.stderr or exc.stdout or "").strip()
            errors.append(f"yt-dlp CLI: {message}")
        except Exception as exc:
            errors.append(f"yt-dlp CLI: {exc}")
    else:
        errors.append("yt-dlp CLI executable not found.")

    # Fallback: try yt_dlp Python module.
    try:
        import yt_dlp  # type: ignore

        ydl_opts = {
            "format": yt_format,
            "quiet": True,
            "no_warnings": True,
        }
        if js_runtime:
            ydl_opts["js_runtimes"] = js_runtime
        if yt_remote_components:
            ydl_opts["remote_components"] = yt_remote_components

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(youtube_url, download=False)
            if isinstance(info, dict):
                direct_url = info.get("url")
                if direct_url:
                    return direct_url, "yt_dlp_module"
                req = info.get("requested_formats")
                if isinstance(req, list):
                    for item in req:
                        if isinstance(item, dict) and item.get("url"):
                            return item["url"], "yt_dlp_module"
        errors.append("yt_dlp module returned no stream URL.")
    except Exception as exc:
        errors.append(f"yt_dlp module: {exc}")

    details = " | ".join(errors)
    raise RuntimeError(f"Cannot resolve YouTube stream URL. {details}")


def choose_video_source(args):
    if args.youtube_url:
        return args.youtube_url, True
    if is_youtube_url(args.input):
        return args.input, True
    return args.input, False


def update_progress(current, total, start_time, status):
    if total > 0:
        draw_progress_bar(current, total, start_time, status)
        return
    elapsed = time.time() - start_time
    try:
        sys.stdout.write(
            f"\rprocessed={current} frames | mode={status:<9} | elapsed={elapsed:7.1f}s"
        )
        sys.stdout.flush()
    except OSError:
        pass


def main():
    args = parse_args()
    if args.every_n_frames < 1:
        raise ValueError("--every-n-frames must be >= 1")
    if args.scale <= 0:
        raise ValueError("--scale must be > 0")

    input_source, is_youtube = choose_video_source(args)
    if is_youtube:
        stream_url, source_type = resolve_youtube_stream_url(
            input_source,
            args.yt_format,
            args.yt_remote_components,
            args.yt_js_runtime,
        )
        print(f"Resolved YouTube stream via {source_type}.")
        cap = cv2.VideoCapture(stream_url)
        display_source = input_source
    else:
        cap = cv2.VideoCapture(input_source)
        display_source = input_source

    if not cap.isOpened():
        raise FileNotFoundError(f"Cannot open input video: {display_source}")

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = float(cap.get(cv2.CAP_PROP_FPS))
    if fps <= 0:
        fps = 30.0

    has_known_total = total_frames > 0
    if has_known_total:
        if args.start_frame < 0 or args.start_frame >= total_frames:
            raise ValueError(f"--start-frame must be in [0, {total_frames - 1}]")
        cap.set(cv2.CAP_PROP_POS_FRAMES, args.start_frame)
        available = total_frames - args.start_frame
        frames_to_process = available if args.max_frames <= 0 else min(args.max_frames, available)
    else:
        if args.start_frame < 0:
            raise ValueError("--start-frame must be >= 0")
        frames_to_process = args.max_frames if args.max_frames > 0 else 0
        skipped = 0
        while skipped < args.start_frame:
            if not cap.grab():
                break
            skipped += 1

    writer = None
    if args.write_video:
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(args.output_video, fourcc, fps, (width, height))

    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    scale_factor = float(args.scale)
    area_factor = scale_factor * scale_factor

    last_pos = None
    velocity = np.array([0.0, 0.0], dtype=np.float64)
    consecutive_misses = 0
    mode = "INIT"
    tracked_rows = 0
    time_zero = None

    start_time = time.time()
    print(f"Processing video: {display_source}")
    if frames_to_process > 0:
        print(f"Frames: {frames_to_process} (start={args.start_frame}, every={args.every_n_frames})")
    else:
        print(f"Frames: unknown total (start={args.start_frame}, every={args.every_n_frames})")

    with open(args.output_csv, "w", newline="") as f:
        csv_writer = csv.writer(f)
        csv_writer.writerow(["Frame", "Time_Sec", "X", "Y", "Mode", "Area", "Circularity"])

        fast_skip = writer is None and args.every_n_frames > 1
        frame_step = args.every_n_frames if fast_skip else 1
        rel_idx = 0
        stop_now = False
        unbounded = frames_to_process <= 0

        while (unbounded or rel_idx < frames_to_process) and not stop_now:
            ok, frame = cap.read()
            if not ok:
                break

            frame_idx = args.start_frame + rel_idx
            raw_timestamp_sec = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
            if not np.isfinite(raw_timestamp_sec) or raw_timestamp_sec < 0:
                raw_timestamp_sec = frame_idx / fps
            if time_zero is None:
                time_zero = raw_timestamp_sec
            timestamp_sec = max(0.0, raw_timestamp_sec - time_zero)
            run_detection = fast_skip or ((rel_idx % args.every_n_frames) == 0)
            display = frame.copy()

            best_target = None
            predicted_pos = None

            if run_detection:
                detect_frame = frame
                if scale_factor != 1.0:
                    detect_frame = cv2.resize(
                        frame,
                        None,
                        fx=scale_factor,
                        fy=scale_factor,
                        interpolation=cv2.INTER_AREA,
                    )
                mask = build_red_mask(detect_frame, clahe, args.min_brightness)
                candidates = contour_candidates(
                    mask,
                    args.min_area * area_factor,
                    args.max_area * area_factor,
                )
                if scale_factor != 1.0:
                    inv_scale = 1.0 / scale_factor
                    for cand in candidates:
                        cand["pos"] = (
                            int(cand["pos"][0] * inv_scale),
                            int(cand["pos"][1] * inv_scale),
                        )
                        cand["area"] = cand["area"] * (inv_scale * inv_scale)

                if consecutive_misses > args.lost_threshold:
                    mode = "LOST"
                elif last_pos is not None:
                    mode = "TRACKING"
                else:
                    mode = "INIT"

                if mode == "TRACKING":
                    pred_xy = np.array(last_pos, dtype=np.float64) + velocity
                    predicted_pos = (int(pred_xy[0]), int(pred_xy[1]))

                    search_radius = args.base_search_radius + int(np.linalg.norm(velocity) * 2)
                    search_radius = min(search_radius, args.max_search_radius)

                    min_dist = float("inf")
                    for cand in candidates:
                        dist = np.linalg.norm(np.array(cand["pos"]) - pred_xy)
                        if dist < search_radius and dist < min_dist:
                            min_dist = dist
                            best_target = cand
                else:
                    best_score = 0.0
                    for cand in candidates:
                        if cand["circ"] <= args.min_circularity:
                            continue
                        score = cand["area"] * cand["circ"]
                        if score > best_score:
                            best_score = score
                            best_target = cand
                    if best_target is not None:
                        mode = "RECOVERED"
                        velocity[:] = 0.0

                if best_target is not None:
                    current_pos = np.array(best_target["pos"], dtype=np.float64)
                    if last_pos is not None and mode == "TRACKING":
                        current_velocity = current_pos - np.array(last_pos, dtype=np.float64)
                        velocity = 0.7 * current_velocity + 0.3 * velocity

                    last_pos = (int(current_pos[0]), int(current_pos[1]))
                    consecutive_misses = 0
                    tracked_rows += 1

                    csv_writer.writerow(
                        [
                            frame_idx,
                            timestamp_sec,
                            last_pos[0],
                            last_pos[1],
                            mode,
                            best_target["area"],
                            best_target["circ"],
                        ]
                    )

                    marker_color = (0, 255, 0) if mode == "TRACKING" else (0, 255, 255)
                    cv2.drawMarker(display, last_pos, marker_color, cv2.MARKER_CROSS, 20, 2)
                    cv2.circle(display, last_pos, 20, marker_color, 1)
                else:
                    consecutive_misses += 1
                    velocity *= 0.9
                    if mode == "LOST":
                        cv2.putText(
                            display,
                            "SEARCHING FULL SCREEN...",
                            (50, 50),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.7,
                            (0, 0, 255),
                            2,
                        )
                    elif predicted_pos is not None:
                        cv2.circle(display, predicted_pos, 30, (255, 0, 0), 1)

            if writer is not None:
                writer.write(display)

            if not args.quiet_progress:
                if unbounded:
                    done_frames = rel_idx + frame_step
                    if done_frames % 30 == 0:
                        update_progress(done_frames, 0, start_time, mode)
                else:
                    done_frames = min(rel_idx + frame_step, frames_to_process)
                    if done_frames % 30 == 0 or done_frames == frames_to_process:
                        update_progress(done_frames, frames_to_process, start_time, mode)

            if fast_skip:
                if unbounded:
                    to_skip = frame_step - 1
                else:
                    to_skip = min(frame_step - 1, frames_to_process - rel_idx - 1)
                skipped = 0
                while skipped < to_skip:
                    if not cap.grab():
                        stop_now = True
                        break
                    skipped += 1
                rel_idx += 1 + skipped
            else:
                rel_idx += 1

    cap.release()
    if writer is not None:
        writer.release()

    print("\nDone.")
    print(f"Tracked points: {tracked_rows}")
    print(f"CSV saved: {args.output_csv}")
    if writer is not None:
        print(f"Video saved: {args.output_video}")


if __name__ == "__main__":
    main()
