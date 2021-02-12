#!/bin/bash

set -o errexit
set -o nounset

if [[ $(id -u) != 0 ]]; then
    exec sudo -- "$0" "$@"
fi

container=bga_discord
owner=$container
srv=/srv/$container

id -u $owner >/dev/null 2>&1 \
    || useradd --create-home --shell=/sbin/nologin $owner
subuid=$(($(grep "^$owner" /etc/subuid | cut -d: -f2) - 1 + 1000))


install --directory --owner=$subuid $srv/var
install --owner=$subuid --group=$owner --mode=u=rw,g=r,o= \
        src/bga_game_list.json $srv/var/
if [[ ! -f $srv/var/keys.py ]]; then
    (
        umask 077
        python -c 'from cryptography.fernet import Fernet; print("FERNET_KEY = %s" % Fernet.generate_key())' >> $srv/keys.py
    )
fi
chown --recursive $subuid:$owner $srv/var
chmod --recursive g-w,o-rwx $srv/var

(
    cd /
    sudo --user=$owner \
         podman create \
                --replace \
                --pull=always \
                --name=$container \
                --mount=type=bind,src=$srv/var,dst=$srv/var,relabel=private \
                --detach \
                --label=io.containers.autoupdate=image \
                ghcr.io/mavit/bga_discord/bga_discord:latest
    sudo --user=$owner \
         podman generate systemd --name $container \
         > /etc/systemd/system/container-$container.service
    perl -MConfig::IniFiles -E 'tie my %service, q(Config::IniFiles), -file => shift; $service{Service}{User} = shift; tied(%service)->RewriteConfig();' /etc/systemd/system/container-$container.service $owner
)

systemctl daemon-reload
systemctl enable --now container-$container.service
