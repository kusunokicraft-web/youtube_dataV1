"""Centralized list of videos to exclude from channel-level analysis.

These are videos that don't represent normal channel performance:
  - Re-upload failures
  - Videos unpublished shortly after release
  - Other anomalies that distort aggregate metrics

Import from individual analysis scripts:
    from _exclusions import EXCLUDED_VIDEO_IDS
"""

EXCLUDED_VIDEO_IDS = {
    "7FyovEYud1A": "再アップ失敗（subs=-1, 925 views, 重複タイトル）",
    "cbEDMw-fPWc": "公開後に非公開化（5 views / 337 日, 重複タイトル）",
    "vp72-fovks4": "公開後に非公開化（17 日, 76 views, perf 0.01x）",
}
