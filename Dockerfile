# ReguLens API.
#
# Builds the corpus and warms every cache at image build time, so a container
# starts in seconds rather than spending ninety of them embedding 954 chunks and
# downloading two models on its first request.
#
# ## This image contains CBUAE text. Do not publish it.
#
# SOURCES.md records that CBUAE terms permit download for non-commercial use but
# not redistribution. The corpus is fetched during the build, so the resulting
# image contains it, and pushing that image to a public registry would be
# redistribution. Keep it in a private registry, or build on the host that runs
# it. The repository itself stays clean: no source document is committed.
#
#   docker build -t regulens .
#   docker run --rm -p 8000:8000 regulens

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HF_HUB_DISABLE_TELEMETRY=1 \
    TOKENIZERS_PARALLELISM=false

WORKDIR /app

# Torch first and CPU-only. The default wheel pulls the CUDA runtime, which adds
# roughly two gigabytes to the image for kernels no server here will run.
RUN pip install --no-cache-dir torch==2.5.1 --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/
COPY scripts/ scripts/
COPY corpus/registry.csv corpus/registry.csv
COPY benchmark/ benchmark/

# Fetch and parse the corpus. Needs network, and honours the same rate limit and
# headers as a local run - see SOURCES.md.
RUN python scripts/download_corpus.py && python scripts/build_corpus.py

# Warm both model downloads and the embedding cache, so the first request pays
# for none of it. Without this the container looks hung for a minute and a half.
RUN python -c "import sys; sys.path.insert(0, 'src'); \
from regulens.api.index import Index, load_chunks; \
i = Index(load_chunks()); \
print('index warm:', i.size, 'chunks, embeddings cached:', i.hybrid.retrievers[1].cached)"

EXPOSE 8000
CMD ["python", "-m", "uvicorn", "regulens.api.app:app", \
     "--app-dir", "src", "--host", "0.0.0.0", "--port", "8000"]
