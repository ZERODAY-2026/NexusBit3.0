#!/usr/bin/env bash
# Privacy proof (Linux): sample every second the TCP connections of python/streamlit/ollama
# processes with `ss` and flag anything that is not loopback.
#   bash scripts/monitor_connections.sh [seconds] [outfile]
SECS=${1:-120}; OUT=${2:-logs/connections.csv}
mkdir -p "$(dirname "$OUT")"
echo "time,line" > "$OUT"
non=0; total=0
for ((i=1; i<=SECS; i++)); do
  while IFS= read -r line; do
    [ -z "$line" ] && continue
    total=$((total+1))
    echo "$(date +%T),\"$line\"" >> "$OUT"
    peer=$(echo "$line" | awk '{print $5}')
    case "$peer" in
      127.*|\[::1\]*|::1*|\[::ffff:127.*) ;;
      *) non=$((non+1)); echo "NON-LOOPBACK: $line" ;;
    esac
  done < <(ss -tnpH state established 2>/dev/null | grep -E 'python|streamlit|ollama')
  printf "\r[%d/%d] connections seen: %d  non-loopback: %d   " "$i" "$SECS" "$total" "$non"
  sleep 1
done
echo
if [ "$non" -eq 0 ]; then echo "RESULT: only loopback connections observed ($total samples). Log: $OUT"
else echo "RESULT: $non non-loopback samples! See $OUT"; exit 1; fi
