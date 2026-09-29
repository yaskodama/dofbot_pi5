#!/bin/bash
# 立方体1個の運搬。$1 = sim（模型） / real（実機）。:8080 の腕窓を経由する。
# 姿勢は 2026-09-27 に模型・実機の双方で 10/10 通った版。
# 指先が机より下に入らないことを確認済み（最低 41.5mm）。
if [ "$1" = "real" ]; then ARGS=(-G "http://localhost:8080/api/arm" --data-urlencode "host=192.168.3.101")
else                       ARGS=(-G "http://localhost:8080/api/arm/sim"); fi
run(){ printf "  %-34s -> " "$1"; curl -s --max-time 12 "${ARGS[@]}" --data-urlencode "cmd=$1" | head -1; }
echo "[1]  原点へ";           run "pose 90 90 90 90 90 30 1500"; sleep 1.8
echo "[2]  グリッパを開く";    run "set 6 30 600";                sleep 0.9
echo "[3]  接近姿勢";         run "pose 90 41 55 15 90 30 1800"; sleep 2.1
echo "[4]  掴む位置へ下降";    run "pose 90 30 60 20 90 30 1500"; sleep 1.8
echo "[5]  掴む";             run "set 6 130 800";               sleep 1.1
echo "[6]  持ち上げる";       run "pose 90 60 50 30 90 130 1500";sleep 1.8
echo "[7]  置き場所へ旋回";    run "pose 30 60 50 30 90 130 1800";sleep 2.1
echo "[8]  下ろす";           run "pose 30 41 55 15 90 130 1500";sleep 1.8
echo "[9]  放す";             run "set 6 30 800";                sleep 1.1
echo "[10] 原点へ";           run "pose 90 90 90 90 90 30 1800"; sleep 2.4
printf "  最終読み戻し -> "; curl -s --max-time 12 "${ARGS[@]}" --data-urlencode "cmd=read"
