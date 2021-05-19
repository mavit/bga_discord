FROM fedora:latest

RUN useradd -m bga_discord

VOLUME /srv/bga_discord/var

ENTRYPOINT ["python3", "-u", "src/main.py"]

RUN \
    yum update -y --setopt=install_weak_deps=False; \
    yum install -y \
        'gcc' \
        'python3-devel' \
        'python3dist(pip)' \
        'python3dist(wheel)' \
    ; \
    yum clean all; \
    rm -rf /var/cache/yum;

COPY ./ /srv/bga_discord/
WORKDIR /srv/bga_discord
RUN pip install -r requirements.txt

RUN ln -sf ../var/bga_game_list.json ../var/bga_keys ../var/keys.py src/
RUN ln -sf var/errs ./

USER bga_discord
