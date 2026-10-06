#!/usr/bin/env bash
#
# Makes the QuickJump popup window behave like a floating HUD on KDE Plasma 6:
#   * always above other windows
#   * visible on every virtual desktop
#   * hidden from the task manager / pager / alt-tab
#   * position and size remembered between sessions (Wayland ignores the
#     position a browser asks for, so KWin has to be the one to remember it)
#   * borderless (no titlebar), resizable below Chrome's minimum size hints —
#     move it with Meta+drag, resize with Meta+right-drag
#
# It also relaxes focus-stealing prevention for Chrome, otherwise clicking a
# quick jump switches the tab without actually raising the browser window.
#
# Usage:  ./install-kwin-rules.sh [--uninstall] [--no-focus-rule]

set -euo pipefail

BAR_ID='1a2b3c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d'
FOCUS_ID='2b3c4d5e-6f7a-4b8c-9d0e-1f2a3b4c5d6e'

BAR_DESC='QuickJump floating bar'
FOCUS_DESC='QuickJump: let Chrome raise its own windows'

UNINSTALL=0
FOCUS_RULE=1
for arg in "$@"; do
  case "$arg" in
    --uninstall) UNINSTALL=1 ;;
    --no-focus-rule) FOCUS_RULE=0 ;;
    -h|--help) sed -n '2,15p' "$0"; exit 0 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

command -v kwriteconfig6 >/dev/null || { echo "kwriteconfig6 not found — is this Plasma 6?" >&2; exit 1; }

kw() { kwriteconfig6 --file kwinrulesrc --group "$1" --key "$2" "$3"; }
kr() { kreadconfig6 --file kwinrulesrc --group "$1" --key "$2" --default "${3-}"; }

# KWin keeps the active rule list in [General]; groups not listed there are ignored.
rules_list() { kr General rules ''; }

register() {
  local id="$1" rules
  rules="$(rules_list)"
  case ",$rules," in
    *",$id,"*) return 0 ;;
  esac
  [[ -n "$rules" ]] && rules="$rules,$id" || rules="$id"
  kw General rules "$rules"
  kw General count "$(awk -F, '{print NF}' <<<"$rules")"
}

RULES_FILE="${XDG_CONFIG_HOME:-$HOME/.config}/kwinrulesrc"

# kwriteconfig6 can only delete individual keys, so drop the whole [group] here.
delete_group() {
  [[ -f "$RULES_FILE" ]] || return 0
  awk -v grp="[$1]" '
    $0 == grp { skip = 1; next }
    /^\[/     { skip = 0 }
    !skip     { print }
  ' "$RULES_FILE" >"$RULES_FILE.qjtmp" && mv "$RULES_FILE.qjtmp" "$RULES_FILE"
}

unregister() {
  local id="$1" rules joined
  local -a parts=() out=()
  rules="$(rules_list)"
  IFS=',' read -ra parts <<<"$rules"
  for p in ${parts[@]+"${parts[@]}"}; do
    [[ -n "$p" && "$p" != "$id" ]] && out+=("$p")
  done
  joined="$(IFS=,; echo "${out[*]-}")"
  kw General rules "$joined"
  kw General count "${#out[@]}"
  delete_group "$id"
}

reload() {
  qdbus6 org.kde.KWin /KWin reconfigure >/dev/null 2>&1 \
    || qdbus org.kde.KWin /KWin reconfigure >/dev/null 2>&1 \
    || echo "note: could not signal KWin — log out and back in to apply."
}

if [[ "$UNINSTALL" == 1 ]]; then
  unregister "$BAR_ID"
  unregister "$FOCUS_ID"
  reload
  echo "QuickJump KWin rules removed."
  exit 0
fi

# --- Rule 1: the floating bar itself ----------------------------------------
# Matched on window title only: the overlay page sets <title>QuickJump Bar</title>
# and Chrome puts that straight into the popup window's title. The hub page is
# titled "QuickJump Hub" precisely so that a normal browser window displaying it
# does not match this rule and get pinned above everything.
kw "$BAR_ID" Description "$BAR_DESC"
kw "$BAR_ID" title 'QuickJump Bar'
# Rule-type values are KWin's SetRule enum: 1=don't affect, 2=force,
# 3=apply initially, 4=remember, 5=apply now, 6=force temporarily.
kw "$BAR_ID" titlematch 2          # 2 = substring match
kw "$BAR_ID" wmclassmatch 0        # 0 = window class unimportant
kw "$BAR_ID" types 1               # 1 = normal windows
kw "$BAR_ID" above true
kw "$BAR_ID" aboverule 2
kw "$BAR_ID" desktops ''           # empty list = all virtual desktops
kw "$BAR_ID" desktopsrule 2
kw "$BAR_ID" skiptaskbar true
kw "$BAR_ID" skiptaskbarrule 2
kw "$BAR_ID" skippager true
kw "$BAR_ID" skippagerrule 2
kw "$BAR_ID" skipswitcher true
kw "$BAR_ID" skipswitcherrule 2
kw "$BAR_ID" positionrule 4        # remember where the user drags it
kw "$BAR_ID" sizerule 4
kw "$BAR_ID" noborder true         # no titlebar/frame — the bar is a HUD
kw "$BAR_ID" noborderrule 2
kw "$BAR_ID" strictgeometry false  # ignore Chrome's minimum-size hints so the
kw "$BAR_ID" strictgeometryrule 2  # bar can be resized down to almost nothing
register "$BAR_ID"

# --- Rule 2: let Chrome pull itself to the front -----------------------------
if [[ "$FOCUS_RULE" == 1 ]]; then
  kw "$FOCUS_ID" Description "$FOCUS_DESC"
  kw "$FOCUS_ID" wmclass '[Gg]oogle-chrome'
  kw "$FOCUS_ID" wmclassmatch 3    # 3 = regular expression
  kw "$FOCUS_ID" wmclasscomplete false
  kw "$FOCUS_ID" types 1
  kw "$FOCUS_ID" fsplevel 0        # 0 = no focus stealing prevention
  kw "$FOCUS_ID" fsplevelrule 2
  register "$FOCUS_ID"
else
  unregister "$FOCUS_ID"
fi

reload

cat <<'DONE'
QuickJump KWin rules installed.

Check them under:
  System Settings → Window Management → Window Rules

If the bar is already open, close and reopen it (× in its header, then toolbar icon → Floating bar) so KWin
applies the rule to a fresh window.

The bar now has no titlebar: move it with Meta+drag, resize with
Meta+right-drag (KDE defaults).
DONE
