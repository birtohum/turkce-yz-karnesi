#!/bin/sh
# Meta modellerini sırayla çalıştırır: önce her model bir kez, sonra ikinci tekrar.
cd "$(dirname "$0")/.."
for rep in 1 2; do
  for m in muse-spark-1.3 muse-spark-1.3-contributor muse-spark-1.2 muse-spark-1.2-contributor muse-spark-1.1 muse-wonder-1.0; do
    PYTHONIOENCODING=utf-8 PYTHONUNBUFFERED=1 .venv/Scripts/python -m karne.run_meta "$m" --rep $rep --workers 7 || echo "HATA $m r$rep"
  done
done
