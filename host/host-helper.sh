#!/usr/bin/env bash
set -Eeuo pipefail
ACTION="${ZMM_ACTION:-audit}"; PROVIDER="${ZMM_PROVIDER:-all}"
DATA=/DATA/AppData/z-mesh-manager
mkdir -p "$DATA"/{config,state,cache,logs,rollback,locks} /DATA/AppData/tailscale /DATA/AppData/netbird
exec 9>"$DATA/locks/host.lock"
flock -w 5 9 || { echo '{"ok":false,"error":"another operation is active"}'; exit 75; }

host_guard() {
  test -d /DATA && mountpoint -q /DATA || { echo "Persistent /DATA is not mounted" >&2; exit 78; }
  test -w /DATA/AppData || { echo "/DATA/AppData is not writable" >&2; exit 78; }
  command -v systemctl >/dev/null && command -v systemd-sysext >/dev/null || { echo "systemd tooling missing" >&2; exit 78; }
}
progress(){ printf '::progress::%s::%s\n' "$1" "$2"; }
json_escape(){ sed ':a;N;$!ba;s/\\/\\\\/g;s/"/\\"/g;s/\n/\\n/g'; }
ts_status(){ /usr/bin/tailscale status --json 2>/dev/null || echo '{}'; }
nb_status(){ /usr/bin/netbird status --json 2>/dev/null || echo '{}'; }

audit() {
  local os="unknown" kernel arch ts_h=false nb_h=false active=""
  os="$(. /etc/os-release 2>/dev/null; echo "${PRETTY_NAME:-unknown}")"; kernel="$(uname -r)"; arch="$(uname -m)"
  systemctl is-active --quiet tailscaled 2>/dev/null && ts_h=true && active=tailscale
  if systemctl is-active --quiet netbird 2>/dev/null; then
    nb_h=true; [[ -n "$active" ]] && active=both || active=netbird
  fi
  printf '{"ok":true,"os":"%s","kernel":"%s","architecture":"%s","active_provider":"%s","storage":{"data_mounted":%s,"tailscale_state":%s,"netbird_state":%s},"tailscale":{"installed":%s,"healthy":%s,"version":"%s"},"netbird":{"installed":%s,"healthy":%s,"version":"%s"}}\n' \
   "$(printf %s "$os"|json_escape)" "$kernel" "$arch" "$active" "$(mountpoint -q /DATA && echo true || echo false)" "$(test -s /DATA/AppData/tailscale/tailscaled.state && echo true || echo false)" "$({ test -s /DATA/AppData/netbird/config.json || test -s /DATA/AppData/netbird/default.json; } && echo true || echo false)" \
   "$(test -x /usr/bin/tailscale && echo true || echo false)" "$ts_h" "$(/usr/bin/tailscale version 2>/dev/null|sed -n '1p'|json_escape)" \
   "$(test -x /usr/bin/netbird && echo true || echo false)" "$nb_h" "$(/usr/bin/netbird version 2>/dev/null|sed -n '1p'|json_escape)"
}

install_tailscale() {
  local ref="${TAILSCALE_SYSEXT_REF:-main}" work; work="$(mktemp -d)"; trap 'rm -rf "$work"' RETURN
  progress 10 "Downloading the Tailscale extension installer"
  curl -fsSL --retry 3 "https://raw.githubusercontent.com/chicohaager/zimaos-tailscale-sysext/${ref}/install.sh" -o "$work/install.sh"
  curl -fsSL --retry 3 "https://raw.githubusercontent.com/chicohaager/zimaos-tailscale-sysext/${ref}/build.sh" -o "$work/build.sh"
  mkdir "$work/systemd"
  for f in tailscaled.service tailscaled-watchdog.service tailscaled-watchdog.timer; do curl -fsSL --retry 3 "https://raw.githubusercontent.com/chicohaager/zimaos-tailscale-sysext/${ref}/systemd/$f" -o "$work/systemd/$f"; done
  chmod +x "$work"/*.sh
  progress 35 "Upstream files downloaded"
  [[ -f /var/lib/extensions/tailscale.raw ]] && cp -f /var/lib/extensions/tailscale.raw "$DATA/rollback/tailscale.raw"
  progress 45 "Building and verifying the Tailscale extension"
  (cd "$work" && ./install.sh </dev/null)
  progress 90 "Tailscale service restarted"
}

install_netbird() {
  local api tag ver machine asset work url sum expected
  machine="$(uname -m)"; [[ "$machine" == x86_64 ]] && asset=amd64 || { [[ "$machine" == aarch64 ]] && asset=arm64 || exit 78; }
  progress 10 "Resolving the latest stable NetBird release"
  api="$(curl -fsSL --retry 3 https://api.github.com/repos/netbirdio/netbird/releases/latest)"
  tag="$(printf %s "$api"|sed -n 's/.*"tag_name": *"\([^"]*\)".*/\1/p'|sed -n 1p)"; ver="${tag#v}"
  work="$(mktemp -d)"; trap 'rm -rf "$work"' RETURN
  url="https://github.com/netbirdio/netbird/releases/download/$tag/netbird_${ver}_linux_${asset}.tar.gz"
  curl -fsSL --retry 3 "$url" -o "$work/netbird.tgz"
  curl -fsSL --retry 3 "https://github.com/netbirdio/netbird/releases/download/$tag/netbird_${ver}_checksums.txt" -o "$work/checksums"
  progress 35 "NetBird package downloaded"
  expected="$(grep "netbird_${ver}_linux_${asset}.tar.gz" "$work/checksums"|awk '{print $1}')"; test -n "$expected"
  echo "$expected  $work/netbird.tgz" | sha256sum -c -
  progress 48 "Checksum verified"
  tar -xzf "$work/netbird.tgz" -C "$work"; test -x "$work/netbird"
  mkdir -p "$work/root/usr/bin" "$work/root/usr/lib/systemd/system" "$work/root/usr/lib/extension-release.d"
  install -m755 "$work/netbird" "$work/root/usr/bin/netbird"
  cat >"$work/root/usr/lib/systemd/system/netbird.service" <<'UNIT'
[Unit]
Description=NetBird client for Z-Mesh Manager
After=network-online.target
Wants=network-online.target
[Service]
Environment=NB_STATE_DIR=/DATA/AppData/netbird
ExecStart=/usr/bin/netbird service run --config /DATA/AppData/netbird/config.json --log-file /DATA/AppData/netbird/client.log --daemon-addr unix:///run/netbird.sock
Restart=on-failure
RestartSec=5
[Install]
WantedBy=multi-user.target
UNIT
  printf 'ID=_any\nARCHITECTURE=%s\nEXTENSION_RELOAD_MANAGER=1\n' "$([[ "$asset" == amd64 ]] && echo x86-64 || echo arm64)" > "$work/root/usr/lib/extension-release.d/extension-release.netbird"
  command -v mksquashfs >/dev/null || { echo "mksquashfs missing" >&2; exit 78; }
  mksquashfs "$work/root" "$work/netbird.raw" -noappend -comp gzip >/dev/null
  progress 72 "System extension built"
  [[ -f /var/lib/extensions/netbird.raw ]] && cp -f /var/lib/extensions/netbird.raw "$DATA/rollback/netbird.raw"
  install -m644 "$work/netbird.raw" /var/lib/extensions/netbird.raw
  cat >/etc/systemd/system/zmm-netbird-watchdog.service <<'UNIT'
[Unit]
Description=Start NetBird after system extensions are merged
After=systemd-sysext.service network-online.target
[Service]
Type=oneshot
ExecStart=/bin/sh -c 'systemctl is-active --quiet netbird || systemctl start netbird'
UNIT
  cat >/etc/systemd/system/zmm-netbird-watchdog.timer <<'UNIT'
[Unit]
Description=NetBird boot-order watchdog
[Timer]
OnBootSec=20s
OnUnitActiveSec=5min
Unit=zmm-netbird-watchdog.service
[Install]
WantedBy=timers.target
UNIT
  systemd-sysext refresh; systemctl daemon-reload; systemctl enable --now netbird zmm-netbird-watchdog.timer
  progress 92 "NetBird service started"
}

do_up() {
  local secret="" secret_file="$DATA/locks/request-credential"
  trap 'rm -f "$secret_file"' EXIT
  if [[ -f "$secret_file" ]]; then
    [[ "$(stat -c '%a' "$secret_file")" == 600 ]] || { echo "Credential file permissions are not 0600" >&2; exit 77; }
    IFS= read -r secret <"$secret_file" || true
  fi
  if [[ "$PROVIDER" == tailscale ]]; then
    progress 20 "Preparing Tailscale authentication"
    systemctl disable --now netbird 2>/dev/null || true
    if [[ -n "$secret" ]]; then /usr/bin/tailscale up --auth-key="file:$secret_file"; else /usr/bin/tailscale up; fi
  else
    progress 20 "Preparing NetBird authentication"
    systemctl disable --now tailscaled 2>/dev/null || true
    local args=(); [[ -n "${ZMM_MANAGEMENT_URL:-}" ]] && args+=(--management-url "$ZMM_MANAGEMENT_URL")
    if [[ -n "$secret" ]]; then /usr/bin/netbird up --setup-key-file "$secret_file" "${args[@]}"; else /usr/bin/netbird up "${args[@]}"; fi
  fi
  rm -f "$secret_file"; secret=""
  progress 90 "Verifying the connection"
  audit
}

uninstall_provider() {
  progress 15 "Stopping $PROVIDER"
  if [[ "$PROVIDER" == tailscale ]]; then
    systemctl disable --now tailscaled tailscaled-watchdog.timer 2>/dev/null || true
    rm -f /etc/systemd/system/tailscaled-watchdog.service /etc/systemd/system/tailscaled-watchdog.timer
  else
    systemctl disable --now netbird zmm-netbird-watchdog.timer 2>/dev/null || true
    rm -f /etc/systemd/system/zmm-netbird-watchdog.service /etc/systemd/system/zmm-netbird-watchdog.timer
  fi
  progress 48 "Removing the system extension"
  rm -f "/var/lib/extensions/$PROVIDER.raw"
  systemd-sysext refresh; systemctl daemon-reload
  progress 90 "Identity retained in /DATA/AppData/$PROVIDER"
}

host_guard
case "$ACTION" in
 audit) audit;;
 install|update) progress 5 "Preparing $PROVIDER"; [[ "$PROVIDER" == tailscale ]] && install_tailscale || install_netbird; progress 96 "Running health checks"; audit;;
 repair) progress 10 "Auditing $PROVIDER"; if [[ "$PROVIDER" == tailscale ]]; then test -x /usr/bin/tailscale || install_tailscale; systemctl restart tailscaled; else test -x /usr/bin/netbird || install_netbird; systemctl restart netbird; fi; progress 90 "Service repaired"; audit;;
 restart) progress 20 "Restarting $PROVIDER"; systemctl restart "$([[ "$PROVIDER" == tailscale ]] && echo tailscaled || echo netbird)"; progress 90 "Checking service health"; audit;;
 up) do_up;;
 down) progress 25 "Disconnecting $PROVIDER"; [[ "$PROVIDER" == tailscale ]] && /usr/bin/tailscale down || /usr/bin/netbird down; progress 90 "Disconnected"; audit;;
 rollback) progress 15 "Loading the previous extension"; test -s "$DATA/rollback/$PROVIDER.raw"; cp -f "$DATA/rollback/$PROVIDER.raw" "/var/lib/extensions/$PROVIDER.raw"; progress 60 "Refreshing system extensions"; systemd-sysext refresh; systemctl daemon-reload; systemctl restart "$([[ "$PROVIDER" == tailscale ]] && echo tailscaled || echo netbird)"; progress 90 "Rollback applied"; audit;;
 uninstall) uninstall_provider; audit;;
 purge) uninstall_provider; progress 94 "Removing saved identity"; rm -rf "/DATA/AppData/$PROVIDER"; mkdir -p "/DATA/AppData/$PROVIDER"; chmod 700 "/DATA/AppData/$PROVIDER"; audit;;
 *) exit 64;;
esac
