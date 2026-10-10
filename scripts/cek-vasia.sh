#!/usr/bin/env bash
# Cek kesehatan host SEBELUM dan SESUDAH setiap deploy Gramasi.
#
# Mesin ini juga melayani VASIA Stationery produksi (vasia.sbs) — container produksinya
# TIDAK punya batas CPU/RAM, jadi Gramasi wajib diperiksa dampaknya.
#
# Pakai:  ./scripts/cek-vasia.sh [catatan]
# Keluar dengan kode 1 kalau ada yang mencurigakan.

set -uo pipefail
CATATAN="${1:-tanpa catatan}"
GAGAL=0

echo "=== pemeriksaan host — ${CATATAN} — $(date '+%Y-%m-%d %H:%M:%S %Z') ==="

# 1. VASIA harus menjawab. 302 = normal (redirect ke halaman login).
echo "--- vasia.sbs"
for i in 1 2 3; do
  HASIL=$(curl -s -o /dev/null -w "%{http_code} %{time_total}" -m 15 https://vasia.sbs || echo "000 -")
  KODE=$(echo "$HASIL" | cut -d' ' -f1)
  WAKTU=$(echo "$HASIL" | cut -d' ' -f2)
  printf "    percobaan %d: HTTP %s · %ss\n" "$i" "$KODE" "$WAKTU"
  case "$KODE" in
    000|5*) GAGAL=1; echo "    ⚠ VASIA tidak sehat!" ;;
  esac
done

# 2. Container produksi lain harus tetap jalan dan tidak di-restart.
echo "--- container produksi (uptime harus panjang, bukan baru restarts)"
for c in wa-hub-app-1 wa-hub-mariadb-1 arka-helpdesk-mysql; do
  S=$(docker inspect "$c" --format '{{.State.Status}} up={{.State.StartedAt}} restarts={{.RestartCount}}' 2>/dev/null || echo "TIDAK ADA")
  echo "    $c: $S"
  case "$S" in TIDAK\ ADA*) GAGAL=1;; esac
done

# 3. Sumber daya host.
echo "--- sumber daya"
free -h | awk '/Mem:/{printf "    RAM: %s total · %s bebas · %s tersedia\n", $2, $4, $7}'
awk '{printf "    load: %s %s %s\n", $1, $2, $3}' /proc/loadavg
df -h / | awk 'NR==2{printf "    disk: %s total · %s bebas (%s terpakai)\n", $2, $4, $5}'

# 4. Container Gramasi, kalau sedang jalan — pastikan batasnya terpasang.
echo "--- container Gramasi (wajib punya batas)"
for c in $(docker ps --format '{{.Names}}' 2>/dev/null | grep -E '^gramasi' || true); do
  docker inspect "$c" --format '    {{.Name}}: cpus={{.HostConfig.NanoCpus}} mem={{.HostConfig.Memory}} shares={{.HostConfig.CpuShares}}' \
    | awk '{ if ($2=="cpus=0" || $3=="mem=0") { print $0 "  ⚠ TANPA BATAS!"; } else print $0 }'
  L=$(docker inspect "$c" --format '{{.HostConfig.NanoCpus}}' 2>/dev/null)
  [ "$L" = "0" ] && GAGAL=1
done

echo
if [ "$GAGAL" = "0" ]; then
  echo "HASIL: semua sehat."
else
  echo "HASIL: ⚠ ADA MASALAH — jangan lanjutkan deploy, periksa dulu."
fi
exit "$GAGAL"
