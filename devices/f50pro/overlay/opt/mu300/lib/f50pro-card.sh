#!/bin/sh
# MU3356 factory wiring positions, not the operator of the installed SIM.
# Selectors are physical levels exposed by the native kernel mux driver.
f50pro_board_id() {
    local root=${MU300_SYSROOT:-} value token path
    if [ -r "$root/proc/driver/board_id" ]; then
        value=$(cat "$root/proc/driver/board_id")
        case $value in 0|1|2|3|4|5) echo "$value"; return;; *) return 1;; esac
    fi
    for path in "$root/proc/cmdline" "$root/proc/device-tree/chosen/bootargs"; do
        [ -r "$path" ] || continue
        for token in $(tr '\000' ' ' < "$path"); do
            case $token in androidboot.zte_boardid=*|zteboot.zte_boardid=*)
                value=${token#*=}
                case $value in 0|1|2|3|4|5) echo "$value"; return;; *) return 1;; esac;;
            esac
        done
    done
    return 1
}
f50pro_cards() {
    case $1 in
        0) echo '0 1 2';;
        1) echo '0 1';;
        2) echo '0 2';;
        3) echo '0 2 3 4';;
        4) echo '0 1 3 4';;
        5) echo '3 4';;
        *) return 1;;
    esac
}
f50pro_card_map() {
    local card
    for card in $(f50pro_cards "$1"); do
        [ "$card" = "$2" ] || continue
        case $1:$card in
            0:0|1:0|2:0|5:3) echo '0 fixed 0';;
            1:1|2:2|5:4) echo '1 fixed 0';;
            0:1) echo '1 chip_select 0';;
            0:2) echo '1 chip_select 1';;
            3:0|4:0) echo '0 psim_select 1';;
            3:2|4:1) echo '1 chip_select 1';;
            3:3|4:3) echo '0 psim_select 0';;
            3:4|4:4) echo '1 chip_select 0';;
            *) return 1;;
        esac
        return
    done
    return 1
}
f50pro_active_card() {
    local card mapping
    # Lookup the board-specific inverse, including card 4 on logical SIM2.
    for card in $(f50pro_cards "$1"); do
        mapping=$(f50pro_card_map "$1" "$card") || return
        case "$mapping:$2:$3:$4" in
            "0 fixed 0:0:"*|"1 fixed 0:1:"*|\
            "0 psim_select 0:0:"*:0|"0 psim_select 1:0:"*:1|\
            "1 chip_select 0:1:0:"*|"1 chip_select 1:1:1:"*) echo "$card"; return;;
        esac
    done
    return 1
}

# Stage an initial preference in a new root, without AT, NV or live UCI writes.
# Both the Android importer and an authorized RAM trial use this same mapping.
f50pro_import_card() {
    local destination=$1 board=$2 card=$3 dsds=${4:-} chip=${5:-} psim=${6:-} mapping stack flags first second
    case $dsds in ''|0|1) ;; *) return 1;; esac
    mapping=$(f50pro_card_map "$board" "$card") || return 1
    stack=${mapping%% *}
    first=; second=
    case "$chip:$psim" in 0:0|0:1|1:0|1:1)
        first=$(f50pro_active_card "$board" 0 "$chip" "$psim") || return 1
        second=$(f50pro_active_card "$board" 1 "$chip" "$psim") || return 1
        case "$stack:$card" in "0:$first"|"1:$second") ;; *) return 1;; esac
        ;;
        :) ;;
        *) return 1;;
    esac
    mkdir -p "$destination/etc/uci-defaults" || return 1
    cat > "$destination/etc/uci-defaults/99-zz-f50pro-card" <<EOF
#!/bin/sh
[ -z "\$(uci -q get unisoc_modem.main.f50pro_card)" ] || exit 0
uci -q set unisoc_modem.main.f50pro_card='$card' &&
uci -q set unisoc_modem.main.data_sim='$stack' &&
uci -q set unisoc_modem.main.dual_standby='0' &&
uci -q commit unisoc_modem
EOF
    if [ -n "$first$second" ]; then
        cat >> "$destination/etc/uci-defaults/99-zz-f50pro-card" <<EOF
[ "\$?" = 0 ] || exit 1
uci -q set unisoc_modem.main.f50pro_route0='$first' &&
uci -q set unisoc_modem.main.f50pro_route1='$second' &&
uci -q commit unisoc_modem || exit 1
EOF
    fi
    # New installations default to single standby, as requested. Import the
    # actual card sources, but do not enable peer RF without an OpenWrt opt-in.
    flags='1 0'; [ "$stack" != 1 ] || flags='0 1'
        cat >> "$destination/etc/uci-defaults/99-zz-f50pro-card" <<EOF
[ "\$?" = 0 ] || exit 1
policy=\${UNISOC_RADIO_POLICY:-/etc/mu300/sim-radio}
if [ ! -e "\$policy" ]; then
    mkdir -p "\$(dirname "\$policy")" || exit 1
    (umask 022; printf '%s\\n' '$flags' > "\$policy") || exit 1
fi
EOF
    chmod 755 "$destination/etc/uci-defaults/99-zz-f50pro-card"
}
