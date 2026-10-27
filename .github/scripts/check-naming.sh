#!/usr/bin/env bash
# Comprueba la convención de nombre de rama y de título de PR (ver CONTRIBUTING.md).
#
# Uso: bash .github/scripts/check-naming.sh "<rama>" "<título del PR>"
#
# Lo llama .github/workflows/pr-hygiene.yml, y sirve igual en local antes de abrir el PR:
#   bash .github/scripts/check-naming.sh "$(git branch --show-current)" "P5-01: repo base"
set -u

# Sin esto, en algunas configuraciones regionales [a-z] también acepta mayúsculas.
export LC_ALL=C

BRANCH="${1:-}"
TITLE="${2:-}"

TYPES='feat|fix|test|chore|docs|refactor|ci|build|perf|style'
# Ticket en ramas (minúsculas) y en títulos. Grupo A: p5-NN / P5-NN. Grupo B: p5-tNN / TNN.
TICKET='t?[0-9]+'
TITLE_TICKET='(P5-[0-9]+|T[0-9]+)'
# p5-01-repo-base · p5-t01-plazos · p5-13-15-metricas-bench · p5-t04-t05-fallas · fix/nombre-corto
BRANCH_RE="^(p5-$TICKET(-$TICKET)*-[a-z0-9]+(-[a-z0-9]+)*|($TYPES)/[a-z0-9]+(-[a-z0-9]+)*)\$"
# P5-01: texto · T01: texto · P5-13/15: texto · P5-13 P5-15: texto · T04 T05: texto
# fix: texto · feat(ui): texto
TITLE_RE="^($TITLE_TICKET(/[0-9]+| $TITLE_TICKET)*|($TYPES)(\\([a-z0-9-]+\\))?): .+"

status=0

if ! [[ "$BRANCH" =~ $BRANCH_RE ]]; then
  echo "::error title=Nombre de rama::'$BRANCH' no sigue la convención. Usa p5-NN-descripcion" \
    "(grupo A), p5-tNN-descripcion (grupo B) o tipo/descripcion con tipo en ($TYPES)," \
    "todo en minúsculas y con guiones. Ver CONTRIBUTING.md." >&2
  status=1
fi

if ! [[ "$TITLE" =~ $TITLE_RE ]]; then
  echo "::error title=Título del PR::'$TITLE' no sigue la convención. Usa 'P5-NN: descripción'" \
    "(grupo A), 'TNN: descripción' (grupo B), varios tickets como 'P5-NN P5-MM: ...' o" \
    "'tipo: descripción' con tipo en ($TYPES). Ver CONTRIBUTING.md." >&2
  status=1
fi

if [[ "$status" -eq 0 ]]; then
  echo "La rama y el título cumplen la convención."
fi
exit "$status"
