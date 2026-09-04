# Z-Mesh Manager

Z-Mesh Manager is a community-built web manager for running **Tailscale or NetBird natively on an immutable NAS host** such as ZimaOS. The UI runs in Docker; the selected VPN client runs on the host through a systemd system extension, so host services such as SMB remain directly reachable.

> Early preview. Tailscale has been validated upstream on ZimaOS 1.7.0. The NetBird sysext still requires real-device validation before production use.

Current container release: `0.1.1`.

## Install

```bash
git clone https://github.com/Chr1s16/z-mesh-manager
cd z-mesh-manager
docker compose pull
docker compose up -d
```

Open `http://YOUR-NAS-IP:8484`.

For local development, use `docker compose -f docker-compose.dev.yml up -d --build`.

## Persistence

- Manager data: `/DATA/AppData/z-mesh-manager/`
- Tailscale identity: `/DATA/AppData/tailscale/`
- NetBird identity: `/DATA/AppData/netbird/`

Enrollment keys are consumed once and are never stored by the manager. Reinstalling a client does not require re-enrollment while its identity directory remains intact.

## Security model

Installing a host system extension requires root-equivalent access. The container therefore uses `privileged: true` and the host PID namespace. Treat this image like a host installer, pin versions, and never expose port 8484 directly to the internet. Z-Mesh Manager exposes a fixed action allowlist and does not mount the Docker socket or provide a web shell.

## Updates

The UI supports install/update, restart, repair, and rollback. Client state is kept outside extension images. Downloads come from the respective upstream projects and are checksum-verified when the upstream publishes a checksum file.

## License and attribution

MIT. Tailscale and NetBird are trademarks of their respective owners. This project is not affiliated with Tailscale, NetBird, IceWhale, or ZimaOS.
