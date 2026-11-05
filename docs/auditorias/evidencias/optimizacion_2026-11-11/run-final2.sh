#!/usr/bin/env bash
cd /tmp/claude-0/-home-user-GlucoLume/41a463d7-d628-543d-81c8-eb20eedfe534/scratchpad/lab
BASE=http://localhost:4177 SCR=/tmp/claude-0/-home-user-GlucoLume/41a463d7-d628-543d-81c8-eb20eedfe534/scratchpad RUNS=10 OUTFILE=final2_s02.jsonl ONLY=escritorio:base,movilLento:base node ayuda-bench.mjs > final2_s02.log 2>&1
echo FINAL2_DONE > /tmp/claude-0/-home-user-GlucoLume/41a463d7-d628-543d-81c8-eb20eedfe534/scratchpad/lab/final2.done
