# arm64-native Infinity embed+rerank server.
# The published michaelf34/infinity:*-cpu image is amd64-only and crash-loops under Rosetta.
# Building from a multi-arch python base gives a true arm64 image; requirements.txt pins the
# exact dependency set the upstream image ships so we don't drift onto incompatible versions.
FROM python:3.11

# libsndfile1: infinity-emb[all] imports soundfile at startup (needs this system C lib).
RUN apt-get update && apt-get install -y --no-install-recommends libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

EXPOSE 7997
ENTRYPOINT ["infinity_emb"]
