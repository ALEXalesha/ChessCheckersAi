#!/usr/bin/env bash
# Публикация на GitHub: https://github.com/ALEXalesha/ChessCheckersAi
#
#   bash tools/publish_github.sh            # только код
#   bash tools/publish_github.sh v1.0.0     # код и тег
#
# Источник правды - Gitea. На GitHub уезжает копия main, в которой личный адрес почты
# автора и коммитера заменён на анонимную почту аккаунта GitHub: почта автора видна любому,
# кто откроет коммит. Рабочая история не трогается, ветка пересобирается каждый раз заново -
# отсюда --force. Первый коммит GitHub (LICENSE и README от создания репозитория) этим
# пушем заменяется историей Gitea.
set -euo pipefail

export PATH="$PATH:/c/Program Files/GitHub CLI"
REPO=ALEXalesha/ChessCheckersAi
# Личный адрес не записан здесь строкой: скрипт берёт его из настроек репозитория.
PRIVATE_EMAIL="$(git config user.email)"
PUBLIC_EMAIL=203467574+ALEXalesha@users.noreply.github.com
# Адрес домашнего Gitea тоже не пишется строкой - только из адреса origin.
LAN_GITEA="$(git remote get-url origin | sed -E 's#^[a-z]+://([^/]+)/.*#\1#')"
PUBLIC_GITEA='gitea.local'
TAG="${1:-}"

cd "$(dirname "$0")/.."

# Третье, чего не должно быть в открытом репозитории: путь к личной папке на ПК. Берётся
# из того, где лежит сам репозиторий (папка над ним), в двух написаниях - со / и с \.
PARENT_DIR="$(cd .. && (pwd -W 2>/dev/null || pwd))"
PARENT_FWD="${PARENT_DIR//\\//}"
PARENT_BACK="${PARENT_FWD//\//\\}"

[ -n "$PRIVATE_EMAIL" ] || { echo "в git config нет user.email - не с чем сверять" >&2; exit 1; }
[ -n "$LAN_GITEA" ] || { echo "нет адреса origin" >&2; exit 1; }

git remote get-url github >/dev/null 2>&1 || git remote add github "https://github.com/$REPO.git"

git branch -f github-main main
FILTER_BRANCH_SQUELCH_WARNING=1 git filter-branch -f --env-filter "
  if [ \"\$GIT_AUTHOR_EMAIL\" = '$PRIVATE_EMAIL' ]; then export GIT_AUTHOR_EMAIL='$PUBLIC_EMAIL'; fi
  if [ \"\$GIT_COMMITTER_EMAIL\" = '$PRIVATE_EMAIL' ]; then export GIT_COMMITTER_EMAIL='$PUBLIC_EMAIL'; fi
" github-main >/dev/null 2>&1
git update-ref -d refs/original/refs/heads/github-main 2>/dev/null || true

# Личное убирается и из содержимого файлов по всей публикуемой истории: почта и адрес
# Gitea заменяются. `|| true`: без совпадений git grep возвращает 1, и при pipefail скрипт
# молча обрывался бы здесь.
DIRTY=$(git grep -I -l -F -e "$PRIVATE_EMAIL" -e "$LAN_GITEA" $(git rev-list github-main) -- 2>/dev/null \
        | sed 's/^[^:]*://' | sort -u | tr '\n' ' ' || true)
if [ -n "$DIRTY" ]; then
  echo "личное в файлах: $DIRTY- переписываю содержимое"
  FILTER_BRANCH_SQUELCH_WARNING=1 git filter-branch -f --index-filter "
    for f in $DIRTY; do
      mode=\$(git ls-tree \$GIT_COMMIT -- \"\$f\" | awk '{print \$1}')
      [ -n \"\$mode\" ] || continue
      blob=\$(git cat-file blob \$GIT_COMMIT:\"\$f\" \
             | sed -e 's/$PRIVATE_EMAIL/$PUBLIC_EMAIL/g' -e 's/$LAN_GITEA/$PUBLIC_GITEA/g' \
             | git hash-object -w --stdin)
      git update-index --cacheinfo \$mode,\$blob,\"\$f\"
    done
  " github-main >/dev/null 2>&1
  git update-ref -d refs/original/refs/heads/github-main 2>/dev/null || true
fi

if git log github-main --format='%ae%n%ce' | grep -qxF "$PRIVATE_EMAIL"; then
  echo "в публикуемой ветке остался личный адрес в авторе коммита - пуш отменён" >&2
  exit 1
fi

# Страж по всей публикуемой истории, а не только по вершине: почта, адрес Gitea, путь к
# личной папке. Путь не переписывается, а останавливает пуш - его надо убрать из файла руками.
if git grep -I -q -F -e "$PRIVATE_EMAIL" -e "$LAN_GITEA" -e "$PARENT_FWD" -e "$PARENT_BACK" \
     $(git rev-list github-main) -- 2>/dev/null; then
  echo "личное осталось в файлах публикуемой истории - пуш отменён" >&2
  git grep -I -l -F -e "$PRIVATE_EMAIL" -e "$LAN_GITEA" -e "$PARENT_FWD" -e "$PARENT_BACK" \
    $(git rev-list github-main) -- | head -5 >&2 || true
  exit 1
fi

echo "ветка github-main: $(git rev-list --count github-main) коммитов, $(git log -1 --format=%h github-main)"
gh auth setup-git
git push github github-main:main --force

if [ -n "$TAG" ]; then
  # Тег ставится прямо на GitHub, без локального: локальный указывал бы на переписанный
  # коммит github-main и путался с тегами Gitea.
  git push github "+github-main:refs/tags/$TAG"
  echo "тег $TAG отправлен"
fi
